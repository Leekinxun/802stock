"""
日志配置模块
提供统一的日志记录功能
"""
import logging
import logging.config
import os
from pathlib import Path
from typing import Optional

import yaml


def setup_logger(
    name: str,
    config_path: Optional[str] = None,
    log_level: Optional[str] = None
) -> logging.Logger:
    """
    设置并返回日志记录器

    Args:
        name: 日志记录器名称
        config_path: 日志配置文件路径
        log_level: 日志级别(DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        配置好的日志记录器
    """
    # 确保日志目录存在
    log_dir = Path(os.getenv('LOG_DIR', 'logs'))
    log_dir.mkdir(parents=True, exist_ok=True)

    # 加载日志配置
    if config_path and Path(config_path).exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            logging.config.dictConfig(config)
    else:
        # 默认配置
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    logger = logging.getLogger(name)

    # 覆盖日志级别
    if log_level:
        logger.setLevel(getattr(logging, log_level.upper()))
    elif os.getenv('LOG_LEVEL'):
        logger.setLevel(getattr(logging, os.getenv('LOG_LEVEL').upper()))

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    获取日志记录器(简化版)

    Args:
        name: 日志记录器名称

    Returns:
        日志记录器
    """
    return logging.getLogger(name)
