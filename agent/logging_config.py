"""
Centralized logging configuration for IRIS.

Sets up rotating file handlers for all logs and errors separately,
with automatic stack trace capture via AutoExcInfoFilter.
"""

import logging
import logging.handlers
import sys
from pathlib import Path


class AutoExcInfoFilter(logging.Filter):
    """
    Automatically captures exception info when logging within an except block.

    When an ERROR-level log is emitted inside an active exception handler,
    this filter populates exc_info from sys.exc_info() if not already set.
    This avoids the need to add exc_info=True to 40+ call sites.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR and record.exc_info is None:
            exc = sys.exc_info()
            if exc[0] is not None:
                record.exc_info = exc
        return True


def configure_logging(
    log_dir: str | None = None,
    log_level: int | None = None
) -> None:
    """
    Initialize logging for IRIS: rotating file handlers + console + auto stack traces.

    Args:
        log_dir: Directory for log files (default: <project_root>/logs)
        log_level: Minimum level for agent logger (default: DEBUG)
    """
    # LOG_LEVEL was documented in .env.example but never read; the level was
    # pinned to DEBUG, which is also why the log files carry every insight the
    # engines considered.
    if log_level is None:
        from .config import settings
        log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Determine log directory
    if log_dir is None:
        log_dir = Path(__file__).parent.parent / "logs"
    else:
        log_dir = Path(log_dir)

    log_dir.mkdir(parents=True, exist_ok=True)

    # Define format
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Create filter
    exc_filter = AutoExcInfoFilter()

    # Get agent package logger
    agent_logger = logging.getLogger("agent")

    # Guard against duplicate handlers (idempotency)
    if len(agent_logger.handlers) > 0:
        return

    # 1. RotatingFileHandler for all logs (DEBUG+)
    all_log_path = log_dir / "iris.log"
    all_handler = logging.handlers.RotatingFileHandler(
        all_log_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5
    )
    all_handler.setLevel(logging.DEBUG)
    all_handler.setFormatter(formatter)
    all_handler.addFilter(exc_filter)
    agent_logger.addHandler(all_handler)

    # 2. RotatingFileHandler for errors only (ERROR+)
    error_log_path = log_dir / "iris_errors.log"
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_path,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    error_handler.addFilter(exc_filter)
    agent_logger.addHandler(error_handler)

    # 3. StreamHandler for console (INFO+)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(exc_filter)
    agent_logger.addHandler(console_handler)

    # Configure agent logger
    agent_logger.setLevel(log_level)
    agent_logger.propagate = False  # Don't propagate to root logger

    # Configure root logger to not spam with library logs
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Convenience wrapper for getting a logger.

    Args:
        name: Logger name (typically __name__)

    Returns:
        A configured logger instance
    """
    return logging.getLogger(name)
