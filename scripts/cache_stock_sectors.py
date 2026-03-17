#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
预加载股票板块信息到数据库

运行方式：
    python scripts/cache_stock_sectors.py
"""

import sys
import logging
from datetime import datetime

sys.path.insert(0, '/Users/berton/Github/daily_stock_analysis')

from src.config import get_config
from data_provider import DataFetcherManager

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def cache_stock_sectors():
    """获取所有持仓股票的板块信息并缓存到数据库"""
    import sqlite3

    # 使用默认数据库路径
    db_path = 'data/stock_analysis.db'
    manager = DataFetcherManager()

    # 获取所有持仓股票
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT symbol, market
        FROM portfolio_trades
        WHERE account_id = 1
        ORDER BY symbol
    """)

    stocks = cursor.fetchall()
    logger.info(f"找到 {len(stocks)} 只股票需要获取板块信息")

    success_count = 0
    failed_count = 0
    cached_count = 0

    for symbol, market in stocks:
        try:
            # 检查是否已缓存（7天内有效）
            cursor.execute("""
                SELECT sector FROM stock_sector_cache
                WHERE symbol = ? AND date(updated_at) > date('now', '-7 days')
            """, (symbol,))
            existing = cursor.fetchone()

            if existing:
                logger.info(f"✓ {symbol} ({existing[0]}) - 已缓存")
                cached_count += 1
                continue

            # 获取板块信息
            boards = manager.get_belong_boards(symbol)

            if boards and len(boards) > 0:
                # 选择主要板块
                sector = boards[0].get('name', 'UNCLASSIFIED')

                # 缓存到数据库
                cursor.execute("""
                    INSERT OR REPLACE INTO stock_sector_cache (symbol, sector, market, updated_at, source)
                    VALUES (?, ?, ?, datetime('now'), 'tushare')
                """, (symbol, sector, market))

                conn.commit()
                success_count += 1
                logger.info(f"✓ {symbol} ({sector}) - 已缓存")
            else:
                logger.warning(f"? {symbol} - 无板块信息")
                failed_count += 1

        except Exception as e:
            logger.error(f"✗ {symbol} - 错误: {e}")
            failed_count += 1

    conn.close()

    logger.info(f"\n=== 缓存完成 ===")
    logger.info(f"新增缓存: {success_count}")
    logger.info(f"已有缓存: {cached_count}")
    logger.info(f"获取失败: {failed_count}")
    logger.info(f"总计: {len(stocks)}")


if __name__ == '__main__':
    cache_stock_sectors()
