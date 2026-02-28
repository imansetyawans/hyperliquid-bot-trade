"""
logger_setup.py
================
Configures logging to both console and file.
"""
import logging
import os
from datetime import datetime

def setup_logger(name: str = "bot", log_dir: str = "logs", level: str = "INFO") -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File (daily rotation by name)
    today = datetime.now().strftime("%Y-%m-%d")
    fh = logging.FileHandler(os.path.join(log_dir, f"bot_{today}.log"), encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
