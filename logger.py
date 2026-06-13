"""
统一日志配置
============
提供全应用共用的日志配置。
所有模块通过 logging.getLogger(__name__) 获取 logger，
日志自动包含时间戳、级别、模块名和行号。
"""

import logging
import sys

# 日志格式: [时间] [级别] [模块:行号] 消息
LOG_FORMAT = "[%(asctime)s] [%(levelname)-7s] [%(name)s:%(lineno)d] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    """配置根日志记录器。

    参数:
        level — 日志级别，默认 INFO。可设 logging.DEBUG 模式进行调试。
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    # 避免重复添加 handler（防止 uvicorn 重载时重复）
    if not root.handlers:
        root.addHandler(handler)

    # 降低第三方库的日志噪音
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
