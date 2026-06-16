# 基于聚宽文章优化：ETF动量轮动策略
# 原始来源：
# https://www.joinquant.com/post/72193  苏董的夏天
# https://www.joinquant.com/post/60824  0xtao
# https://www.joinquant.com/post/42673  wywy1995
#
# 核心优化：
# 1. 事件驱动调仓：每天检查，但只在触发条件满足时才换仓
#    - 标的替换触发：新标的得分超过当前持仓得分一定比例
#    - 权重漂移触发：实际仓位偏离目标仓位超过阈值
#    - 止损触发：持仓标的动量崩溃或组合回撤超限
#    - 最长持仓天数兜底：防止长期不调仓
# 2. 持有数量可配置，按动量强度比例分配仓位
# 3. 修复原始策略缺少 import math 的 bug
# 4. 提取公共评分函数，消除重复代码
# 5. get_rank2 中 continue 导致 NaN 行问题修复
# 6. FixedSlippage → PriceRelatedSlippage
# 7. print → log.info

# ======================== 策略参数配置 ========================
# 持有得分最高的N只ETF，按动量强度比例分配仓位
# 1 = 集中持仓，收益弹性大但回撤深
# 2 = 平衡收益与分散（推荐）
# 3+ = 更分散但单标的贡献降低
TARGET_NUM = 2

# --- 事件驱动调仓参数 ---
# 标的替换触发：新标的得分 / 当前最弱持仓得分 > 此值才换仓
# 1.0 = 只要排名变就换（等同日频），1.2 = 新标的需强20%（推荐），越大越保守
REPLACE_THRESHOLD = 1.2

# 权重漂移触发：实际仓位与目标仓位偏差超过此比例时再平衡
# 0.05 = 偏离5%就调（灵敏），0.15 = 偏离15%才调（推荐）
DRIFT_THRESHOLD = 0.15

# 组合最大回撤止损：从最近高点回撤超过此比例时清仓
# 0.10 = 回撤10%清仓，0 = 不启用
MAX_DRAWDOWN_STOP = 0.10

# 单标的动量崩溃止损：持仓标的当日得分降为0时立即卖出
# True = 启用（推荐），False = 不启用
MOMENTUM_CRASH_STOP = True

# 最长持仓天数：超过此天数未调仓则强制检查一次
# 防止市场长期平稳导致仓位僵化，10 = 10个交易日
MAX_HOLD_DAYS = 10

# 调仓执行时间
REBALANCE_TIME = '9:40'

# --- 动量计算参数 ---
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

    # 事件驱动调仓状态
    g.last_rebalance_date = None   # 上次调仓日期
    g.skip_count = 0               # 连续无操作次数（交易日计数）
    g.peak_value = None            # 组合历史最高净值（惰性初始化）

    log.info(f"策略参数: 持有{g.target_num}只, 动态回看={'开' if g.auto_day else '关'}"
             f"({g.min_days}~{g.max_days})")
    log.info(f"调仓触发: 替换>{REPLACE_THRESHOLD}, 漂移>{DRIFT_THRESHOLD:.0%},"
             f" 回撤止损{MAX_DRAWDOWN_STOP:.0%}, 最长{MAX_HOLD_DAYS}天")

    run_daily(check_and_trade, REBALANCE_TIME)


def _calc_score(prices):
    """对价格序列计算动量得分 = 年化收益率 × R²

    使用加权线性回归（权重从1线性递增到2，近期权重大），
    斜率转换为年化收益率，R²衡量趋势可靠性。
    """
    if len(prices) < 4:
        return 0

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
    """固定回看期动量评分，返回 (etf_list, score_list, score_map)"""
    scores = {}
    current_data = get_current_data()
    for etf in etf_pool:
        df = attribute_history(etf, g.m_days, "1d", ["close"])
        prices = np.append(df["close"].values, current_data[etf].last_price)
        scores[etf] = _calc_score(prices)

    etf_list, score_list = _ranked_scores(scores)
    return etf_list, score_list, scores


def get_rank2(etf_pool):
    """ATR动态回看期动量评分，返回 (etf_list, score_list, score_map)"""
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

    etf_list, score_list = _ranked_scores(scores)
    return etf_list, score_list, scores


def _compute_target():
    """计算目标持仓列表和权重，返回 (etf_list, score_list, weights, score_map)"""
    if g.auto_day:
        etf_list, score_list, score_map = get_rank2(g.etf_pool)
    else:
        etf_list, score_list, score_map = get_rank(g.etf_pool)

    etf_list = etf_list[:g.target_num]
    score_list = score_list[:g.target_num]

    if not etf_list:
        return [], [], [], {}

    total_score = sum(score_list)
    weights = [s / total_score for s in score_list]
    return etf_list, score_list, weights, score_map


def _check_drawdown_stop(context):
    """组合回撤止损：从峰值回撤超过阈值则清仓"""
    if MAX_DRAWDOWN_STOP <= 0:
        return False

    current_value = context.portfolio.total_value
    if g.peak_value is None:
        g.peak_value = current_value

    g.peak_value = max(g.peak_value, current_value)
    drawdown = 1 - current_value / g.peak_value

    if drawdown >= MAX_DRAWDOWN_STOP and context.portfolio.positions:
        log.info(f"⚠ 组合回撤止损: 回撤{drawdown:.1%} >= {MAX_DRAWDOWN_STOP:.1%}，清仓")
        for etf in list(context.portfolio.positions):
            order_target_value(etf, 0)
        g.peak_value = current_value
        return True
    return False


def _check_momentum_crash(context, target_etfs, target_scores):
    """动量崩溃止损：持仓标的中得分降为0的立即卖出"""
    if not MOMENTUM_CRASH_STOP:
        return False

    crashed = []
    for etf in list(context.portfolio.positions):
        if etf in target_etfs:
            idx = target_etfs.index(etf)
            if target_scores[idx] == 0:
                crashed.append(etf)

    if crashed:
        log.info(f"⚠ 动量崩溃止损: {crashed} 得分为0，立即卖出")
        for etf in crashed:
            order_target_value(etf, 0)
        return True
    return False


def _need_replace(context, target_etfs, score_map):
    """标的替换触发：新标的得分需显著超过当前最弱持仓才换仓"""
    holds = list(context.portfolio.positions)
    if not holds:
        return True

    if set(holds) == set(target_etfs):
        return False

    leaving = [etf for etf in holds if etf not in target_etfs]
    if not leaving:
        return True

    weakest_hold_score = min(score_map.get(etf, 0) for etf in leaving)
    entering = [etf for etf in target_etfs if etf not in holds]
    if not entering:
        return True
    best_new_score = max(score_map.get(etf, 0) for etf in entering)

    if weakest_hold_score > 0 and best_new_score / weakest_hold_score < REPLACE_THRESHOLD:
        log.info(f"⏸ 不换仓: 新标的最高分{best_new_score:.2f} / 持仓最低分{weakest_hold_score:.2f}"
                 f" = {best_new_score / weakest_hold_score:.2f} < {REPLACE_THRESHOLD}")
        return False

    return True


def _need_rebalance(context, target_etfs, target_weights):
    """权重漂移触发：实际仓位偏离目标仓位超过阈值时再平衡"""
    total_value = context.portfolio.total_value
    if total_value == 0:
        return False

    for etf, target_w in zip(target_etfs, target_weights):
        if etf in context.portfolio.positions:
            current_value = context.portfolio.positions[etf].value
        else:
            current_value = 0
        current_w = current_value / total_value
        if abs(current_w - target_w) > DRIFT_THRESHOLD:
            return True
    return False




def check_and_trade(context):
    """事件驱动调仓：每天检查触发条件，满足时才执行"""
    # 1. 组合回撤止损（最高优先级）
    if _check_drawdown_stop(context):
        return

    # 2. 计算目标持仓
    target_etfs, target_scores, target_weights, score_map = _compute_target()
    if not target_etfs:
        log.info("无合格标的，维持当前持仓")
        return

    # 3. 动量崩溃止损
    if _check_momentum_crash(context, target_etfs, target_scores):
        target_etfs, target_scores, target_weights, score_map = _compute_target()
        if not target_etfs:
            return

    # 4. 判断是否需要调仓
    today = context.current_dt.date()
    if g.last_rebalance_date is None:
        days_since_rebalance = MAX_HOLD_DAYS  # 首日强制触发
    else:
        days_since_rebalance = (today - g.last_rebalance_date).days
        # 自然日差 × 0.7 ≈ 交易日数（保守估计）
        days_since_rebalance = int(days_since_rebalance * 0.7)

    holds = list(context.portfolio.positions)
    is_empty = len(holds) == 0

    should_rebalance = is_empty \
        or _need_replace(context, target_etfs, score_map) \
        or _need_rebalance(context, target_etfs, target_weights) \
        or days_since_rebalance >= MAX_HOLD_DAYS

    if not should_rebalance:
        return

    # 5. 执行调仓
    log.info(f"🔄 调仓触发 (空仓={is_empty}, 距上次={days_since_rebalance}天)")

    for etf in holds:
        if etf not in target_etfs:
            order_target_value(etf, 0)
            log.info(f"  卖出 {etf}")

    for etf, weight in zip(target_etfs, target_weights):
        target_value = context.portfolio.total_value * weight
        order_target_value(etf, target_value)

    g.last_rebalance_date = today
    log.info("  " + " | ".join(
        f"{etf} {w:.0%}" for etf, w in zip(target_etfs, target_weights)
    ))
