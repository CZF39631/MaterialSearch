"""
数据库迁移脚本：v1 → v2
变更内容：
1. 新增 scan_meta 表（用于追踪索引版本）

使用方法：
    python migrate_v1_to_v2.py
"""
import logging
import sys

from config import SQLALCHEMY_DATABASE_URL
from models import ScanMeta, engine
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """执行迁移"""
    logger.info(f"数据库路径: {SQLALCHEMY_DATABASE_URL}")

    # 创建 scan_meta 表（如果不存在）
    logger.info("创建 scan_meta 表...")
    ScanMeta.__table__.create(bind=engine, checkfirst=True)
    logger.info("scan_meta 表创建完成")

    # 确认 WAL 模式
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA journal_mode"))
        mode = result.fetchone()[0]
        logger.info(f"当前 journal_mode: {mode}")
        if mode.lower() != "wal":
            conn.execute(text("PRAGMA journal_mode=WAL"))
            logger.info("已切换到 WAL 模式")

    logger.info("迁移完成！")


if __name__ == "__main__":
    migrate()
