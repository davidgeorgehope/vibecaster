import logging
import sys
from logging.handlers import RotatingFileHandler
import os

# Determine the root directory (parent of backend)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(ROOT_DIR, "logs")

# Ensure logs directory exists
os.makedirs(LOGS_DIR, exist_ok=True)

# Log file paths
APP_LOG = os.path.join(LOGS_DIR, "vibecaster.log")
AGENT_LOG = os.path.join(LOGS_DIR, "agent_cycles.log")
ERROR_LOG = os.path.join(LOGS_DIR, "errors.log")


def setup_logger(name: str, log_file: str = None, level=logging.INFO) -> logging.Logger:
    """
    Set up a logger with both file and console handlers.

    Args:
        name: Logger name (usually __name__)
        log_file: Path to log file (default: APP_LOG)
        level: Logging level

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers if logger already exists
    if logger.handlers:
        return logger

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (rotating, max 10MB, keep 5 backups)
    if log_file is None:
        log_file = APP_LOG

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Error file handler (errors only)
    error_handler = RotatingFileHandler(
        ERROR_LOG,
        maxBytes=10 * 1024 * 1024,
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    return logger


# Create default loggers
app_logger = setup_logger("vibecaster.app", APP_LOG)
agent_logger = setup_logger("vibecaster.agent", AGENT_LOG)
