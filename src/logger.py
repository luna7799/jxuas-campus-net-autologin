# -*- coding: utf-8 -*-
"""
logger.py —— 日志模块
======================
同时输出到控制台与文件；文件按 1MB 滚动、最多保留 3 份，
位于 <基目录>/logs/autologin.log。
"""
import logging
import os
from logging.handlers import RotatingFileHandler

from config import get_base_dir


def setup_logger(log_cfg):
    """按配置构建全局 logger（避免重复添加 handler）。"""
    logger = logging.getLogger("jxuas")
    if logger.handlers:
        return logger

    level = getattr(logging, str(log_cfg.get("level", "INFO")).upper(), logging.INFO)
    logger.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    # 控制台输出
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    # 文件输出（按 1MB 滚动，保留 3 份）
    log_dir = os.path.join(get_base_dir(), log_cfg.get("log_dir", "logs"))
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "autologin.log"),
        maxBytes=1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
