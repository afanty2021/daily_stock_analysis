#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补充缓存剩余股票的板块信息
"""

import sys
import sqlite3

sys.path.insert(0, '/Users/berton/Github/daily_stock_analysis')

from data_provider import DataFetcherManager

def cache_remaining_stocks():
    db_path = 'data/stock_analysis.db'
    manager = DataFetcherManager()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ETF 分类映射
    etf_sectors = {
        '512000': '券商ETF',
        '512890': '红利ETF',
        '513120': '新能源ETF',
        '513130': '科技ETF',
        '513180': '红利ETF',
        '513330': 'AI应用ETF',
        '513880': 'ETF',
        '516880': 'ETF',
        '588000': 'ETF',
        '688729': 'ETF',
        '688775': 'ETF',
    }

    # 未缓存的股票
    uncached = [
        '00883', '03800', '159201', '159399', '159864',
        '512000', '512890', '513120', '513130', '513180',
        '513330', '513880', '516880', '588000', '688729', '688775'
    ]

    success = 0
    failed = 0

    for symbol in uncached:
        # ETF 使用预设分类
        if symbol in etf_sectors:
            sector = etf_sectors[symbol]
            cursor.execute("""
                INSERT OR REPLACE INTO stock_sector_cache (symbol, sector, market, updated_at, source)
                VALUES (?, ?, 'cn', datetime('now'), 'manual')
            """, (symbol, sector))
            conn.commit()
            print(f"✓ {symbol} ({sector}) - ETF预设")
            success += 1
            continue

        # 尝试从 API 获取（设置较短超时）
        try:
            boards = manager.get_belong_boards(symbol)
            if boards:
                sector = boards[0].get('name', 'UNCLASSIFIED')
                cursor.execute("""
                    INSERT OR REPLACE INTO stock_sector_cache (symbol, sector, market, updated_at, source)
                    VALUES (?, ?, 'cn', datetime('now'), 'tushare')
                """, (symbol, sector))
                conn.commit()
                print(f"✓ {symbol} ({sector})")
                success += 1
            else:
                # 无法获取，标记为未分类
                cursor.execute("""
                    INSERT OR REPLACE INTO stock_sector_cache (symbol, sector, market, updated_at, source)
                    VALUES (?, 'UNCLASSIFIED', 'cn', datetime('now'), 'manual')
                """, (symbol,))
                conn.commit()
                print(f"? {symbol} (UNCLASSIFIED)")
                failed += 1
        except Exception as e:
            print(f"✗ {symbol} - {e}")
            failed += 1

    conn.close()
    print(f"\n完成: {success} 成功, {failed} 失败/未分类")

if __name__ == '__main__':
    cache_remaining_stocks()
