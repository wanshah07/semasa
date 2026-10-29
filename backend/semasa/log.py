"""One logger, plain lines, UTC stamps. GitHub Actions shows stdout; nothing fancier is needed."""

from __future__ import annotations

import logging
import sys
import time


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter("%(asctime)sZ %(levelname)s %(name)s: %(message)s", "%Y-%m-%dT%H:%M:%S")
        fmt.converter = time.gmtime      # the line says Z, so the clock is UTC wherever this runs, not the machine's zone
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
