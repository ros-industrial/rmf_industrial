"""VDA5050 master service — FastAPI app."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import api_router
from .config import _MODE, settings
from .database import init_db
from .db_models import AgvRecord  # noqa: F401 — registers table with Base
from .logger import setup_logging
from .master import make_master
from .transport import (
    Heartbeat,
    ServerTransportAmqp,
    ServerTransportBase,
    ServerTransportZenoh,
)

config = settings()

# disable docs for prod
_docs_url = None if _MODE == "prod" else "/docs"
_redoc_url = None if _MODE == "prod" else "/redoc"

_TOPIC_PREFIX = "rmf2_vda5050_master/v1"


def _build_transport() -> ServerTransportBase | None:
    if config.transport is None:
        return None
    if config.transport == "amqp":
        return ServerTransportAmqp.from_url(config.amqp.url, config.amqp.exchange)
    if config.transport == "zenoh":
        return (
            ServerTransportZenoh.from_endpoints(config.zenoh.endpoints)
            if config.zenoh.endpoints
            else ServerTransportZenoh()
        )
    raise ValueError(f"Unknown transport: {config.transport!r}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    app.state.layout_result = None

    transport = _build_transport()
    app.state.transport = transport

    heartbeat = Heartbeat(config.heartbeat_interval)

    with init_db(config.database_url) as session_factory:
        app.state.session_factory = session_factory
        with make_master(
            config,
            session_factory,
            transport,
            topic_prefix=_TOPIC_PREFIX,
            heartbeat=heartbeat,
        ) as master:
            app.state.master = master
            heartbeat.start()
            yield
            heartbeat.stop()


app = FastAPI(lifespan=lifespan, docs_url=_docs_url, redoc_url=_redoc_url, root_path=config.root_path)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
