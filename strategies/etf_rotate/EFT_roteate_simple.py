# 克隆自聚宽文章：https://www.joinquant.com/post/72193
# 标题：已经用于实战了！模拟******跟踪9个月 40%收益
# 作者：苏董的夏天

# 克隆自聚宽文章：https://www.joinquant.com/post/60824
# 标题：【思路分享】动量ETF轮动之基于历史波动率动态调整历史回溯期
# 作者：0xtao

# 克隆自聚宽文章：https://www.joinquant.com/post/42673
# 标题：【回顾3】ETF策略之核心资产轮动
# 作者：wywy1995

import numpy as np
import pandas as pd
import talib


# 初始化函数
def initialize(context):
    # 设定基准
    set_benchmark('000300.XSHG')
    # 用真实价格交易
    set_option('use_real_price', True)
    # 打开防未来函数
    set_option("avoid_future_data", True)
    # 设置滑点 https://www.joinquant.com/view/community/detail/a31a822d1cfa7e83b1dda228d4562a70
    set_slippage(FixedSlippage(0.001))
    # 设置交易成本
    set_order_cost(
        OrderCost(open_tax=0, close_tax=0, open_commission=0.0002, close_commission=0.0002, close_today_commission=0,
                  min_commission=1), type='fund')
    # 过滤一定级别的日志
    log.set_level('system', 'error')
    # 参数
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
        '159915.XSHE',  # 创业板100
    ]
    g.m_days = 25  # 默认动量参考天数
    g.auto_day = True  # 是否自动根据历史波动率动态调整动量的lookback天数
    g.min_days = 20  # 最小lookback天数
    g.max_days = 60  # 最大lookback天数

    run_daily(trade, '9:40')  # 每天运行确保即时捕捉动量变化


# 基于年化收益和判定系数打分的动量因子轮动 https://www.joinquant.com/post/26142
def get_rank(etf_pool):
    data = pd.DataFrame(index=etf_pool, columns=["annualized_returns", "r2", "score"])
    current_data = get_current_data()
    for etf in etf_pool:
        # 获取数据
        df = attribute_history(etf, g.m_days, "1d", ["close", "high"])
        prices = np.append(df["close"].values, current_data[etf].last_price)

        # 设置参数
        y = np.log(prices)
        x = np.arange(len(y))
        weights = np.linspace(1, 2, len(y))

        # 计算年化收益率
        slope, intercept = np.polyfit(x, y, 1, w=weights)
        data.loc[etf, "annualized_returns"] = math.exp(slope * 250) - 1

        # 计算R²
        ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
        ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
        data.loc[etf, "r2"] = 1 - ss_res / ss_tot if ss_tot else 0

        # 计算得分
        data.loc[etf, "score"] = data.loc[etf, "annualized_returns"] * data.loc[etf, "r2"]

        # 过滤近3日跌幅超过5%的ETF
        if min(prices[-1] / prices[-2], prices[-2] / prices[-3], prices[-3] / prices[-4]) < 0.95:
            data.loc[etf, "score"] = 0

    # log.info(data)

    # 过滤ETF，并按得分降序排列
    data = data.query("0 < score < 6").sort_values(by="score", ascending=False)

    return data.index.tolist()


def get_rank2(etf_pool):
    data = pd.DataFrame(index=etf_pool, columns=["annualized_returns", "r2", "score"])
    current_data = get_current_data()
    for etf in etf_pool:
        # 获取数据
        df = attribute_history(etf, g.max_days + 10, "1d", ["close", "high", "low"])

        # 过滤历史数据不足的标的
        if len(df) < (g.max_days + 10) or df["low"].isna().sum() > g.max_days or df[
            "close"].isna().sum() > g.max_days or df["high"].isna().sum() > g.max_days:
            continue

        # 基于ATR
        long_atr = talib.ATR(df["high"], df["low"], df["close"], timeperiod=g.max_days)
        short_atr = talib.ATR(df["high"], df["low"], df["close"], timeperiod=g.min_days)
        # print(long_atr[-1])
        # print(short_atr[-1])
        lookback = int(g.min_days + (g.max_days - g.min_days) * (1 - min(0.9, short_atr[-1] / long_atr[-1])))

        # 原文是基于每日收盘收益率标准差来计算波动率
        # https://mp.weixin.qq.com/s/bzMeZA97uB9O0GtCcxHHsw?click_id=3
        # df['return'] = df['close'].pct_change()
        # long_vol = float(np.std(df['return'][:], ddof=1))
        # short_vol = float(np.std(df['return'][-g.min_days:], ddof=1))
        # # print(long_vol)
        # # print(short_vol)
        # lookback = int(g.min_days + (g.max_days - g.min_days) * (1 - min(0.9, short_vol/long_vol)))

        prices = np.append(df["close"].values, current_data[etf].last_price)
        prices = prices[-lookback:]
        log.info(f"{etf} lookback days :{lookback}, {len(prices)}")

        # 设置参数
        y = np.log(prices)
        x = np.arange(len(y))
        weights = np.linspace(1, 2, len(y))

        # 计算年化收益率
        slope, intercept = np.polyfit(x, y, 1, w=weights)
        data.loc[etf, "annualized_returns"] = math.exp(slope * 250) - 1

        # 计算R²
        ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
        ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
        data.loc[etf, "r2"] = 1 - ss_res / ss_tot if ss_tot else 0

        # 计算得分
        data.loc[etf, "score"] = data.loc[etf, "annualized_returns"] * data.loc[etf, "r2"]

        # 过滤近3日跌幅超过5%的ETF
        if min(prices[-1] / prices[-2], prices[-2] / prices[-3], prices[-3] / prices[-4]) < 0.95:
            data.loc[etf, "score"] = 0

    # log.info(data)

    # 过滤ETF，并按得分降序排列
    data = data.query("0 < score < 6").sort_values(by="score", ascending=False)

    return data.index.tolist()


# 交易
def trade(context):
    # 获取动量最高的一只ETF
    target_num = 1
    if g.auto_day:
        target_list = get_rank2(g.etf_pool)[:target_num]
    else:
        target_list = get_rank(g.etf_pool)[:target_num]
    # 卖出
    hold_list = list(context.portfolio.positions)
    for etf in hold_list:
        if etf not in target_list:
            order_target_value(etf, 0)
            print('卖出' + str(etf))
        else:
            print('继续持有' + str(etf))
    # 买入
    hold_list = list(context.portfolio.positions)
    if len(hold_list) < target_num:
        value = context.portfolio.available_cash / (target_num - len(hold_list))
        for etf in target_list:
            if context.portfolio.positions[etf].total_amount == 0:
                order_target_value(etf, value)
                print('买入' + str(etf))

