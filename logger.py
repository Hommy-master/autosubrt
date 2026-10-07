import logging
from logging.config import dictConfig
import os

import config

# 日志文件名，轮转后为 autosubrt.log.1 ~ autosubrt.log.<LOG_BACKUP_COUNT>
LOG_FILE_NAME = "autosubrt.log"


class RelativePathFormatter(logging.Formatter):
    def __init__(self, *args, project_root: str = None, **kwargs):
        super().__init__(*args, **kwargs)
        # 把项目根目录传进来
        self.project_root = project_root or os.getcwd()

    def format(self, record: logging.LogRecord) -> str:
        record.rel_path = os.path.relpath(record.pathname, self.project_root)
        return super().format(record)

# 文件处理器在 dictConfig 阶段就会打开文件，目录不存在会直接抛错，先建好
os.makedirs(config.LOG_DIR, exist_ok=True)

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": RelativePathFormatter,
            "fmt": "%(asctime)s.%(msecs)03d | %(levelname)s | %(name)s | %(rel_path)s:%(lineno)d | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
        # 落盘日志：单个文件超过 LOG_MAX_BYTES 后轮转，最多保留 LOG_BACKUP_COUNT 个历史文件
        "file": {
            "formatter": "default",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(config.LOG_DIR, LOG_FILE_NAME),
            "maxBytes": config.LOG_MAX_BYTES,
            "backupCount": config.LOG_BACKUP_COUNT,
            # 容器内 locale 不是 UTF-8，不指定编码时写中文日志会抛 UnicodeEncodeError
            "encoding": "utf-8",
        },
    },
    "root": {
        "handlers": ["default", "file"],
        "level": "INFO"
    },
    "loggers": {
        "uvicorn": {"handlers": ["default", "file"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["default", "file"], "level": "INFO", "propagate": False},
        "autosubrt": {"handlers": ["default", "file"], "level": "INFO", "propagate": False}
    },
}

dictConfig(LOGGING_CONFIG)

logger = logging.getLogger(__name__)
