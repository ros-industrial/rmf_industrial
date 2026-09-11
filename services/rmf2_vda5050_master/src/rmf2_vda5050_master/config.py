from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    CliSettingsSource,
    DotEnvSettingsSource,
    EnvSettingsSource,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from .models import AgvConfig

_MODE = os.environ.get("MODE", "dev")
_ENV_FILES = [".env", f".env.{_MODE}"]
_TOML_FILES = ["config.toml", f"config.{_MODE}.toml"]


class AmqpSettings(BaseModel):
    """AMQP transport connection settings.

    TOML::

        [amqp]
        url = "amqp://guest:guest@localhost/"
        exchange = "rmf2"

    Env vars (prefix ``RMF2_VM__AMQP__``)::

        RMF2_VM__AMQP__URL=amqp://guest:guest@localhost/
        RMF2_VM__AMQP__EXCHANGE=rmf2
    """

    url: str = "amqp://guest:guest@localhost/"
    exchange: str = "rmf2"


class ZenohSettings(BaseModel):
    """Zenoh transport connection settings.

    TOML::

        [zenoh]
        endpoints = ["tcp/localhost:7447"]

    Env vars (prefix ``RMF2_VM__ZENOH__``)::

        RMF2_VM__ZENOH__ENDPOINTS=["tcp/localhost:7447"]

    Leave ``endpoints`` empty to use the default Zenoh peer-to-peer discovery.
    """

    endpoints: list[str] = Field(default_factory=list)


class Settings(BaseSettings):
    """RMF2 VDA5050 Master service configuration.

    Settings are loaded in priority order: CLI args > env vars > .env file > config.toml > defaults.

    Environment-specific overrides are selected via the MODE env var (default: dev):
      .env.<MODE>        e.g. .env.dev, .env.staging, .env.prod
      config.<MODE>.toml e.g. config.dev.toml, config.staging.toml, config.prod.toml

    AGV configurations are best defined in config.<MODE>.toml as [[agvs]] tables.
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        env_prefix="RMF2_VM__",
        env_nested_delimiter="__",
        toml_file=_TOML_FILES,
    )

    database_url: str = Field(
        default="sqlite:///./rmf2_vda5050_master.db",
        description="SQLAlchemy database URL. Defaults to a local SQLite file; use a postgresql:// URL for PostgreSQL",
    )
    mqtt_broker: str = Field(description="MQTT broker URI (e.g. tcp://localhost:1883)")
    master_mqtt_client_id: str | None = Field(
        default=None,
        description="MQTT client ID used by this master node. Defaults to rmf2-vda5050-master if not set",
    )
    agvs: list[AgvConfig] = Field(
        default=[],
        description="List of AGVs to onboard. Preferred: config.<MODE>.toml [[agvs]] table",
    )
    host: str = Field(description="Host address for the FastAPI server to bind to")
    port: int = Field(description="Port for the FastAPI server to listen on")
    root_path: str = Field(default="", description="ASGI root_path when running behind a reverse proxy with a path prefix (e.g. /rmf2_vda5050_master)")
    cors_origins: list[str] = Field(default=["*"], description="Allowed CORS origins")
    transport: Literal["amqp", "zenoh"] | None = Field(
        default=None,
        description="Transport backend to use. One of: amqp, zenoh. Omit or set to null to run without a transport (HTTP-only mode).",
    )
    amqp: AmqpSettings = Field(
        default_factory=AmqpSettings, description="AMQP transport connection settings"
    )
    zenoh: ZenohSettings = Field(
        default_factory=ZenohSettings, description="Zenoh transport connection settings"
    )
    heartbeat_interval: float = Field(
        default=5.0,
        description="Interval in seconds for heartbeat callbacks. Set to 0 to disable.",
    )
    map_mode: Literal["local", "server"] = Field(
        default="local",
        description=(
            "'local': load LIF from map_path at startup (optional); REST POST /layout also available. "
            "'server': fetch LIF from a live external map server at map_url at startup."
        ),
    )
    map_path: Path | None = Field(
        default=None,
        description="(local mode) Path to a LIF (Layout Interchange Format) JSON file to load at startup",
    )
    map_server_url: str | None = Field(
        default=None,
        description="(server mode) URL of a live external map server to fetch the LIF JSON from at startup",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: InitSettingsSource,
        env_settings: EnvSettingsSource,
        dotenv_settings: DotEnvSettingsSource,
        **_: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            CliSettingsSource(settings_cls, cli_parse_args=True, cli_kebab_case=True),
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            init_settings,
        )


@lru_cache
def settings() -> Settings:
    return Settings()
