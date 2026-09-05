"""Centralized logging configuration."""
import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    # Configures stdout logging exactly once so every module gets consistent, timestamped output.
    root = logging.getLogger()
    if root.handlers:  # already configured (e.g. under reload/tests)
        root.setLevel(level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    # Returns a named logger so each module's log lines are attributable to their source.
    return logging.getLogger(name)
