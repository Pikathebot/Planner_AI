import logging
import datetime
from logging.handlers import RotatingFileHandler

# --- CONFIG ---
LOG_FILE = "log.txt"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3

# Setup the shared rotating handler
_handler = RotatingFileHandler(LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(message)s"))

_logger = logging.getLogger("persistent_logger")
_logger.setLevel(logging.INFO)
_logger.addHandler(_handler)

def log_run(goal: str, task_type: str, model: str, plan: str):
    """Log a generated plan to the rotating log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    separator = "=" * 60
    entry = (
        f"\n{separator}\n"
        f"TYPE      : PLAN\n"
        f"Timestamp : {timestamp}\n"
        f"Goal      : {goal}\n"
        f"Task Type : {task_type}\n"
        f"Model     : {model}\n"
        f"{'-' * 60}\n"
        f"{plan}\n"
    )
    _logger.info(entry)

def log_chat(message: str, model: str, response: str):
    """Log a chat interaction to the rotating log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    separator = "=" * 60
    entry = (
        f"\n{separator}\n"
        f"TYPE      : CHAT\n"
        f"Timestamp : {timestamp}\n"
        f"Model     : {model}\n"
        f"User      : {message}\n"
        f"{'-' * 60}\n"
        f"Assistant : {response}\n"
    )
    _logger.info(entry)
