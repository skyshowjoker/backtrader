# 克隆自聚宽文章：https://www.joinquant.com/post/72633
# 标题：年化19500%可以跑着玩，但是不要用这个策略******
# 作者：汐屿

from jqdata import *
import pandas as pd
import numpy as np

def initialize(context):
    set_benchmark('000905.XSHG')
    set_option('use_real_price', True)
    log.set_level('order', 'error')

    set_order_cost(
        OrderCost(
            close_tax=0.001,
            open_commission=0.0003,
            close_commission=0.0003,
            min_commission=5
        ),
        type='stock'
    )

    g.index_code = '000905.XSHG'   # 中证500
    g.max_hold_num = 5             # 最多持有5只
    g.window = 20                  # 平台窗口
    g.volume_multiplier = 1.5      # 放量倍数
    g.min_list_days = 250          # 上市至少250天
    g.min_money = 3e7              # 近20日平均成交额至少3000万
    g.hold_days = {}               # 记录持仓天数

    run_daily(market_open, time='09:35', reference_security='000905.XSHG')


def market_open(context):
    sell_expired_positions(context)
    buy_new_positions(context)


def sell_expired_positions(context):
    current_holds = list(context.portfolio.positions.keys())

    for stock in current_holds:
        if stock not in g.hold_days:
            g.hold_days[stock] = 1
        else:
            g.hold_days[stock] += 1

        if g.hold_days[stock] >= 2:
            order_target(stock, 0)
            log.info('卖出到期持仓: {}'.format(stock))

    # 清理已经卖掉的记录
    current_holds_after = list(context.portfolio.positions.keys())
    to_delete = []
    for stock in g.hold_days:
        if stock not in current_holds_after:
            to_delete.append(stock)
    for stock in to_delete:
        del g.hold_days[stock]


def buy_new_positions(context):
    current_holds = list(context.portfolio.positions.keys())
    available_slots = g.max_hold_num - len(current_holds)

    if available_slots <= 0:
        return

    stocks = get_index_stocks(g.index_code)
    stocks = filter_stocks(context, stocks)

    if len(stocks) == 0:
        return

    signal_list = select_signal_stocks(context, stocks)

    if len(signal_list) == 0:
        log.info('今日无信号股票')
        return

    buy_list = [s for s in signal_list if s not in current_holds][:available_slots]

    if len(buy_list) == 0:
        return

    cash = context.portfolio.available_cash
    if cash <= 0:
        return

    per_value = cash / len(buy_list)

    for stock in buy_list:
        order_value(stock, per_value)
        g.hold_days[stock] = 0
        log.info('买入股票: {}'.format(stock))


def filter_stocks(context, stocks):
    current_data = get_current_data()
    filtered = []

    for s in stocks:
        if current_data[s].paused:
            continue
        if current_data[s].is_st:
            continue
        if 'ST' in current_data[s].name:
            continue
        if '*' in current_data[s].name:
            continue
        if '退' in current_data[s].name:
            continue

        info = get_security_info(s)
        if (context.current_dt.date() - info.start_date).days < g.min_list_days:
            continue

        filtered.append(s)

    if len(filtered) == 0:
        return []

    money_df = get_price(
        filtered,
        end_date=context.current_dt,
        frequency='daily',
        fields=['money'],
        count=20,
        panel=False
    )

    avg_money = money_df.groupby('code')['money'].mean()
    filtered = [s for s in filtered if s in avg_money.index and avg_money[s] >= g.min_money]

    return filtered


def select_signal_stocks(context, stocks):
    price_df = get_price(
        stocks,
        end_date=context.current_dt,
        frequency='daily',
        fields=['close', 'high', 'volume', 'money'],
        count=g.window + 2,
        panel=False
    )

    if price_df is None or len(price_df) == 0:
        return []

    signal_list = []

    for code, group in price_df.groupby('code'):
        group = group.sort_values('time').reset_index(drop=True)

        if len(group) < g.window + 1:
            continue

        prev_data = group.iloc[:-1]
        today = group.iloc[-1]

        platform_high = prev_data['high'].tail(g.window).max()
        avg_volume = prev_data['volume'].tail(g.window).mean()

        if avg_volume <= 0:
            continue

        cond_break = today['close'] > platform_high
        cond_volume = today['volume'] >= avg_volume * g.volume_multiplier

        if cond_break and cond_volume:
            breakout_strength = today['close'] / platform_high - 1
            signal_list.append((code, breakout_strength))

    signal_list = sorted(signal_list, key=lambda x: x[1], reverse=True)
    return [x[0] for x in signal_list]