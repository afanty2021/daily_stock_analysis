#!/usr/bin/env python3
"""
流水账转换脚本
将原始流水帐.xls 转换为系统可导入的 CSV 格式

转换规则:
- 买入股票/卖出股票 → 交易记录 (side=buy/sell)
- 股票分红 → 现金分红记录 (side 为空，作为 cash_ledger 处理)
- 送股 → 企业行为 (corporate_action with bonus_share)
- 投入资金 → 现金流水 (cash_ledger with direction=in)
"""

import pandas as pd
from datetime import datetime
from collections import defaultdict
import sys


def parse_chinese_date(date_str: str) -> str:
    """将中文日期转换为 YYYY-MM-DD 格式"""
    if not date_str or pd.isna(date_str):
        return ""

    # 移除"年""月""日"并替换为"-"
    date_str = str(date_str).strip()
    date_str = date_str.replace('年', '-').replace('月', '-').replace('日', '')
    return date_str


def validate_no_oversell(records: list) -> list:
    """
    验证每个股票的买卖记录，检测是否存在超卖情况
    返回超卖警告列表
    """
    warnings = []

    # 按股票分组记录
    stock_records = defaultdict(list)
    for record in records:
        symbol = record.get('证券代码')
        if symbol:
            stock_records[symbol].append(record)

    # 检查每个股票
    for symbol, recs in stock_records.items():
        # 按日期排序
        recs_sorted = sorted(recs, key=lambda x: x.get('成交日期', ''))

        running_balance = 0.0
        for rec in recs_sorted:
            side = rec.get('买卖方向')
            qty = float(rec.get('成交数量') or 0)
            date = rec.get('成交日期')

            if side == 'buy':
                running_balance += qty
            elif side == 'sell':
                if qty > running_balance:
                    warnings.append(
                        f"⚠️  超卖检测：{symbol} 在 {date} 卖出 {qty} 股，但当时持仓仅 {running_balance:.0f} 股"
                    )
                running_balance -= qty
            elif side == 'bonus':
                running_balance += qty

        if running_balance < 0:
            warnings.append(f"⚠️  {symbol}: 最终持仓为负数 ({running_balance:.0f} 股)，数据可能不完整")

    return warnings


def convert_ledger(input_file: str = '流水帐.xls', output_file: str = '流水账_转换.csv'):
    """转换流水账文件"""

    # 读取原始文件
    with open(input_file, 'r', encoding='gbk') as f:
        content = f.read()

    lines = content.strip().split('\n')

    # 解析表头
    header = lines[0].split('\t')
    header = [col.replace('="', '').replace('"', '') for col in header]
    # 移除空列
    header = [col for col in header if col]

    # 解析数据行
    data = []
    for line in lines[1:]:
        if line.strip():
            row = line.split('\t')
            row = [col.replace('="', '').replace('"', '') if col else '' for col in row]
            # 确保列数一致
            while len(row) < len(header):
                row.append('')
            data.append(row[:len(header)])

    df = pd.DataFrame(data, columns=header)

    print(f"读取到 {len(df)} 条原始记录")
    print(f"账目类型分布: {df['账目类型'].value_counts().to_dict()}")
    print("---")

    # 转换后的数据
    converted_records = []

    for idx, row in df.iterrows():
        account_type = row['账目类型']
        trade_date = parse_chinese_date(row['时间'])
        symbol = str(row['股票代码']).strip() if pd.notna(row['股票代码']) else ""
        name = str(row['股票名称']).strip() if pd.notna(row['股票名称']) else ""
        quantity = str(row['交易量']).strip() if pd.notna(row['交易量']) else ""
        price = str(row['交易价']).strip() if pd.notna(row['交易价']) else ""
        fee = str(row['手续费']).strip() if pd.notna(row['手续费']) else "0"
        cash_flow = str(row['现金流量']).strip() if pd.notna(row['现金流量']) else ""

        # 跳过无股票代码的记录（如投入资金）
        if not symbol and account_type == '投入资金':
            # 投入资金作为现金流水
            converted_records.append({
                '成交日期': trade_date,
                '证券代码': '',
                '买卖方向': '',
                '成交数量': '',
                '成交价格': '',
                '成交编号': f'cash_in_{idx}',
                '账目类型': account_type,
                '现金流量': cash_flow,
                '备注': '投入资金'
            })
            continue

        if account_type == '买入股票':
            converted_records.append({
                '成交日期': trade_date,
                '证券代码': symbol,
                '买卖方向': 'buy',
                '成交数量': quantity,
                '成交价格': price,
                '成交编号': f'trade_{idx}',
                '账目类型': account_type,
                '现金流量': '',
                '备注': name
            })

        elif account_type == '卖出股票':
            converted_records.append({
                '成交日期': trade_date,
                '证券代码': symbol,
                '买卖方向': 'sell',
                '成交数量': quantity,
                '成交价格': price,
                '成交编号': f'trade_{idx}',
                '账目类型': account_type,
                '现金流量': '',
                '备注': name
            })

        elif account_type == '股票分红':
            # 股票分红：空方向，作为现金分红处理
            converted_records.append({
                '成交日期': trade_date,
                '证券代码': symbol,
                '买卖方向': '',  # 空方向表示现金分红
                '成交数量': quantity,  # 分红股票数
                '成交价格': price,  # 每股分红额
                '成交编号': f'dividend_{idx}',
                '账目类型': account_type,
                '现金流量': cash_flow,  # 分红金额
                '备注': f'{name} 分红'
            })

        elif account_type == '送股':
            # 送股：企业行为，需要特殊标记
            converted_records.append({
                '成交日期': trade_date,
                '证券代码': symbol,
                '买卖方向': 'bonus',  # 特殊标记为企业行为
                '成交数量': quantity,
                '成交价格': '',
                '成交编号': f'bonus_{idx}',
                '账目类型': account_type,
                '现金流量': '',
                '备注': f'{name} 送股'
            })

    # 创建 DataFrame 并保存
    converted_df = pd.DataFrame(converted_records)
    converted_df.to_csv(output_file, index=False, encoding='utf-8-sig')

    print(f"转换完成！共 {len(converted_df)} 条记录")
    print(f"输出文件：{output_file}")
    print("---")
    print("转换后账目类型分布:")
    print(converted_df['账目类型'].value_counts())

    # 显示送股记录
    bonus_records = converted_df[converted_df['账目类型'] == '送股']
    if len(bonus_records) > 0:
        print("---")
        print("送股记录详情:")
        print(bonus_records)

    # 超卖检测
    print("---")
    oversell_warnings = validate_no_oversell(converted_records)
    if oversell_warnings:
        print("⚠️  检测到超卖情况：")
        for warning in oversell_warnings:
            print(warning)
        print(f"\n共 {len(oversell_warnings)} 条超卖警告，请检查原始数据！")
    else:
        print("✅ 超卖检测：未发现超卖情况")

    return converted_df


if __name__ == '__main__':
    convert_ledger()
