"""Console + file logging helpers (keep console concise)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_run_logging(run_dir: Path, *, level: int = logging.INFO) -> logging.Logger:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("raven_mcs")
    logger.handlers.clear()
    logger.setLevel(level)
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = logging.FileHandler(run_dir / "stdout.log", encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    err_handler = logging.FileHandler(run_dir / "stderr.log", encoding="utf-8")
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(fmt)
    logger.addHandler(err_handler)

    return logger
