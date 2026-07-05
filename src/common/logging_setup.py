"""Console + per-stage file logging (logs/<stage>.log)."""

import logging

from src.common.config import LOGS_DIR

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def get_logger(name: str, logfile: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(_FORMAT)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    if logfile:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(LOGS_DIR / logfile)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger
