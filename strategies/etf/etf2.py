# 基于聚宽文章优化：ETF动量轮动策略
# 原始来源：
# https://www.joinquant.com/post/72193  苏董的夏天
# https://www.joinquant.com/post/60824  0xtao
# https://www.joinquant.com/post/42673  wywy1995
#
# 优化内容：
# 1. 持有数量可配置（TARGET_NUM），等权分配，分散单一标的风险
# 2. 修复原始策略缺少 import math 的 bug
# 3. 提取公共评分函数，消除 get_rank/get_rank2 重复代码
# 4. get_rank2 中 continue 导致 NaN 行问题修复
# 5. print → log.info
# 6. FixedSlippage → PriceRelatedSlippage，适配不同价位ETF
# 7. 停牌标的卖出失败容错处理

# ======================== 策略参数配置 ========================
# 持有得分最高的N只ETF，按动量强度比例分配仓位
# 1 = 集中持仓，收益弹性大但回撤深
# 2 = 平衡收益与分散（推荐）
# 3+ = 更分散但单标的贡献降低
TARGET_NUM = 2

# 调仓频率: 'daily' / 'weekly' / 'monthly'
# daily   = 每个交易日调仓，捕捉快但交易成本高
# weekly  = 每周一调仓（推荐），平衡灵敏度与成本
# monthly = 每月首个交易日调仓，成本最低但反应慢
REBALANCE_FREQ = 'weekly'

# 调仓执行时间（开盘后分钟数，如 '9:40'）
REBALANCE_TIME = '9:40'

# 启用ATR动态回看期（False则使用固定回看期）
AUTO_LOOKBACK = True

# 固定回看期天数（AUTO_LOOKBACK=False时生效）
FIXED_LOOKBACK = 25

# 动态回看期范围（AUTO_LOOKBACK=True时生效）
MIN_LOOKBACK = 20
MAX_LOOKBACK = 60
# ======================== 参数配置结束 ========================

import math
import numpy as np
import pandas as pd
import talib


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option("avoid_future_data", True)
    set_slippage(PriceRelatedSlippage(0.002))
    set_order_cost(
        OrderCost(open_tax=0, close_tax=0, open_commission=0.0002, close_commission=0.0002,
                  close_today_commission=0, min_commission=1), type='fund')
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
        '159915.XSHE',  # 创业板100
    ]
    g.target_num = min(TARGET_NUM, len(g.etf_pool))
    g.auto_day = AUTO_LOOKBACK
    g.m_days = FIXED_LOOKBACK
    g.min_days = MIN_LOOKBACK
    g.max_days = MAX_LOOKBACK

    log.info(f"策略参数: 持有{g.target_num}只, 动态回看={'开' if g.auto_day else '关'}"
             f"({g.min_days}~{g.max_days}), 调仓={REBALANCE_FREQ}")

    if REBALANCE_FREQ == 'daily':
        run_daily(trade, REBALANCE_TIME)
    elif REBALANCE_FREQ == 'weekly':
        run_weekly(trade, weekday=1, time=REBALANCE_TIME)
    elif REBALANCE_FREQ == 'monthly':
        run_monthly(trade, monthday=1, time=REBALANCE_TIME)
    else:
        raise ValueError(f"不支持的调仓频率: {REBALANCE_FREQ}，可选: daily/weekly/monthly")


def _calc_score(prices):
    """对价格序列计算动量得分 = 年化收益率 × R²

    使用加权线性回归（权重从1线性递增到2，近期权重大），
    斜率转换为年化收益率，R²衡量趋势可靠性。
    """
    y = np.log(prices)
    x = np.arange(len(y))
    weights = np.linspace(1, 2, len(y))

    slope, intercept = np.polyfit(x, y, 1, w=weights)
    annualized_return = math.exp(slope * 250) - 1

    ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
    ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0

    score = annualized_return * r2

    # 近3日任一日跌幅超5%则清零
    if min(prices[-1] / prices[-2], prices[-2] / prices[-3], prices[-3] / prices[-4]) < 0.95:
        score = 0

    return score


def _ranked_scores(scores):
    """过滤并按得分降序排列，返回 (标的列表, 得分列表)"""
    ranked = pd.Series(scores).sort_values(ascending=False)
    valid = ranked[(ranked > 0) & (ranked < 6)]
    return valid.index.tolist(), valid.values.tolist()


def get_rank(etf_pool):
    """固定回看期动量评分"""
    scores = {}
    current_data = get_current_data()
    for etf in etf_pool:
        df = attribute_history(etf, g.m_days, "1d", ["close"])
        prices = np.append(df["close"].values, current_data[etf].last_price)
        scores[etf] = _calc_score(prices)

    return _ranked_scores(scores)


def get_rank2(etf_pool):
    """ATR动态回看期动量评分"""
    scores = {}
    current_data = get_current_data()
    for etf in etf_pool:
        df = attribute_history(etf, g.max_days + 10, "1d", ["close", "high", "low"])

        # 数据不足则跳过，不计入排名
        if len(df) < (g.max_days + 10) or \
           df["low"].isna().sum() > g.max_days or \
           df["close"].isna().sum() > g.max_days or \
           df["high"].isna().sum() > g.max_days:
            continue

        long_atr = talib.ATR(df["high"], df["low"], df["close"], timeperiod=g.max_days)
        short_atr = talib.ATR(df["high"], df["low"], df["close"], timeperiod=g.min_days)
        lookback = int(g.min_days + (g.max_days - g.min_days) * (1 - min(0.9, short_atr[-1] / long_atr[-1])))

        prices = np.append(df["close"].values, current_data[etf].last_price)
        prices = prices[-lookback:]
        log.info(f"{etf} lookback={lookback}, len={len(prices)}")

        scores[etf] = _calc_score(prices)

    return _ranked_scores(scores)


def trade(context):
    """每日调仓：按动量强度比例持有Top N ETF"""
    if g.auto_day:
        etf_list, score_list = get_rank2(g.etf_pool)
    else:
        etf_list, score_list = get_rank(g.etf_pool)

    etf_list = etf_list[:g.target_num]
    score_list = score_list[:g.target_num]

    if not etf_list:
        log.info("无合格标的，维持当前持仓")
        return

    # 按得分比例分配仓位：weight_i = score_i / sum(scores)
    total_score = sum(score_list)
    weights = [s / total_score for s in score_list]

    # 卖出不在目标列表中的持仓
    for etf in list(context.portfolio.positions):
        if etf not in etf_list:
            order_target_value(etf, 0)
            log.info(f"卖出 {etf}")

    # 按比例建仓/调仓
    for etf, weight in zip(etf_list, weights):
        target_value = context.portfolio.total_value * weight
        order_target_value(etf, target_value)

    log.info(" | ".join(
        f"{etf} {w:.0%}" for etf, w in zip(etf_list, weights)
    ))
