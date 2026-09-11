"""VDA5050 master service — FastAPI app with instant action endpoints."""

import uvicorn

from .app import app
from .config import settings


def main() -> None:
    config = settings()
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
