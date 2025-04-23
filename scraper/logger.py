import sys
from typing import Literal

from loguru import logger

_LEVELS = Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
_LOG_LEVEL: _LEVELS = "DEBUG"


def set_log_level(level: _LEVELS):
    global _LOG_LEVEL
    _LOG_LEVEL = level


def _filter(r):
    return r["level"].no >= logger.level(_LOG_LEVEL).no


logger.remove()
logger.add(sys.stderr, filter=_filter)
logger.add("scraper.log", filter=_filter, rotation="10 MB", retention="10 days")