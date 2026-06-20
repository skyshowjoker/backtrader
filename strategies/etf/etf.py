# 克隆自聚宽文章：https://www.joinquant.com/post/72193
# 标题：已经用于实战了！模拟******跟踪9个月 40%收益
# 作者：苏董的夏天
#
# 克隆自聚宽文章：https://www.joinquant.com/post/60824
# 标题：【思路分享】动量ETF轮动之基于历史波动率动态调整历史回溯期
# 作者：0xtao
#
# 克隆自聚宽文章：https://www.joinquant.com/post/42673
# 标题：【回顾3】ETF策略之核心资产轮动
# 作者：wywy1995

import numpy as np
import pandas as pd
import talib


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option("avoid_future_data", True)
    set_slippage(FixedSlippage(0.001))
    set_order_cost(
        OrderCost(open_tax=0, close_tax=0, open_commission=0.0002, close_commission=0.0002, close_today_commission=0,
                  min_commission=1), type='fund')
    log.set_level('system', 'error')

    g.etf_pool = [
        # 境外
        "513100.XSHG",  # 纳指ETF
        "513520.XSHG",  # 日经ETF
        "513030.XSHG",  # 德国ETF
        # 商品
        "518880.XSHG",  # 黄金ETF
        "159980.XSHE",  # 有色ETF
        "159985.XSHE",  # 豆粕ETF
        "501018.XSHG",  # 南方原油
        # 债券
        "511090.XSHG",  # 30年国债ETF
        # 国内
        "513130.XSHG",  # 恒生科技
        "512890.XSHG",  # 红利低波
        '159915.XSHE',  # 创业板
        '510300.XSHG',    # 沪深300
    ]
    g.m_days = 25
    g.auto_day = True
    g.min_days = 20
    g.max_days = 60

    run_daily(trade, '9:40')


def get_rank(etf_pool):
    """基于年化收益×R²打分的固定回看期动量轮动"""
    data = pd.DataFrame(index=etf_pool, columns=["annualized_returns", "r2", "score"])
    current_data = get_current_data()
    for etf in etf_pool:
        df = attribute_history(etf, g.m_days, "1d", ["close", "high"])
        prices = np.append(df["close"].values, current_data[etf].last_price)

        y = np.log(prices)
        x = np.arange(len(y))
        weights = np.linspace(1, 2, len(y))

        slope, intercept = np.polyfit(x, y, 1, w=weights)
        data.loc[etf, "annualized_returns"] = math.exp(slope * 250) - 1

        ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
        ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
        data.loc[etf, "r2"] = 1 - ss_res / ss_tot if ss_tot else 0

        data.loc[etf, "score"] = data.loc[etf, "annualized_returns"] * data.loc[etf, "r2"]

        if min(prices[-1] / prices[-2], prices[-2] / prices[-3], prices[-3] / prices[-4]) < 0.95:
            data.loc[etf, "score"] = 0

    data = data.query("0 < score < 6").sort_values(by="score", ascending=False)
    return data.index.tolist()


def get_rank2(etf_pool):
    """基于ATR动态调整回看期的动量轮动"""
    data = pd.DataFrame(index=etf_pool, columns=["annualized_returns", "r2", "score"])
    current_data = get_current_data()
    for etf in etf_pool:
        df = attribute_history(etf, g.max_days + 10, "1d", ["close", "high", "low"])

        if len(df) < (g.max_days + 10) or df["low"].isna().sum() > g.max_days or df[
            "close"].isna().sum() > g.max_days or df["high"].isna().sum() > g.max_days:
            continue

        long_atr = talib.ATR(df["high"], df["low"], df["close"], timeperiod=g.max_days)
        short_atr = talib.ATR(df["high"], df["low"], df["close"], timeperiod=g.min_days)
        lookback = int(g.min_days + (g.max_days - g.min_days) * (1 - min(0.9, short_atr[-1] / long_atr[-1])))

        prices = np.append(df["close"].values, current_data[etf].last_price)
        prices = prices[-lookback:]
        log.info(f"{etf} lookback days :{lookback}, {len(prices)}")

        y = np.log(prices)
        x = np.arange(len(y))
        weights = np.linspace(1, 2, len(y))

        slope, intercept = np.polyfit(x, y, 1, w=weights)
        data.loc[etf, "annualized_returns"] = math.exp(slope * 250) - 1

        ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
        ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
        data.loc[etf, "r2"] = 1 - ss_res / ss_tot if ss_tot else 0

        data.loc[etf, "score"] = data.loc[etf, "annualized_returns"] * data.loc[etf, "r2"]

        if min(prices[-1] / prices[-2], prices[-2] / prices[-3], prices[-3] / prices[-4]) < 0.95:
            data.loc[etf, "score"] = 0

    data = data.query("0 < score < 6").sort_values(by="score", ascending=False)
    return data.index.tolist()


def trade(context):
    """每日调仓：持有动量最高的1只ETF"""
    target_num = 1
    if g.auto_day:
        target_list = get_rank2(g.etf_pool)[:target_num]
    else:
        target_list = get_rank(g.etf_pool)[:target_num]

    for etf in list(context.portfolio.positions):
        if etf not in target_list:
            order_target_value(etf, 0)
            print('卖出' + str(etf))
        else:
            print('继续持有' + str(etf))

    hold_list = list(context.portfolio.positions)
    if len(hold_list) < target_num:
        value = context.portfolio.available_cash / (target_num - len(hold_list))
        for etf in target_list:
            if context.portfolio.positions[etf].total_amount == 0:
                order_target_value(etf, value)
                print('买入' + str(etf))
