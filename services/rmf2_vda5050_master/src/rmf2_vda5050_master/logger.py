from __future__ import annotations

import logging


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
