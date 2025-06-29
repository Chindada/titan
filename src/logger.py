import logging
import os
from datetime import datetime
from logging import LogRecord


class RFC3339Formatter(logging.Formatter):
    def __init__(self, is_file: bool = False):
        self.log_format = "%(levelname)s\x1b[0m[TIT][%(asctime)s] %(message)s"
        self.is_file = is_file
        if is_file:
            self.log_format = "%(levelname)s[TIT][%(asctime)s] %(message)s"
        super().__init__(self.log_format)

    def format(self, record: LogRecord) -> str:
        if self.is_file:
            return super().format(record)

        color_code = "\x1b[36m"
        if record.levelno == logging.DEBUG:
            color_code = "\x1b[37m"
        elif record.levelno == logging.INFO:
            color_code = "\x1b[36m"
        elif record.levelno == logging.WARNING:
            color_code = "\x1b[33m"
        elif record.levelno == logging.ERROR:
            color_code = "\x1b[31m"
        elif record.levelno == logging.CRITICAL:
            color_code = "\x1b[31m"
        return f"{color_code}{super().format(record)}"

    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created).astimezone().strftime("%Y-%m-%d %H:%M:%S")


console_handler = logging.StreamHandler()
console_handler.setFormatter(RFC3339Formatter(is_file=False))

root_dir = os.path.dirname(os.path.abspath(__file__))
file_handler = logging.FileHandler(os.path.join(root_dir, "..", "logs", f'{datetime.now().strftime("%Y-%m-%d")}.log'))
file_handler.setFormatter(RFC3339Formatter(is_file=True))

logging.addLevelName(50, "CRIT")
logging.addLevelName(40, "ERRO")
logging.addLevelName(30, "WARN")
logging.addLevelName(20, "INFO")
logging.addLevelName(10, "DEBU")

logger = logging.getLogger()
logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.setLevel(logging.INFO)
