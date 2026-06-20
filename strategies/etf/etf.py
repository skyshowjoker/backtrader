# ============================================================================
# ETF 动量轮动策略
# ============================================================================
# 融合三篇聚宽社区文章的思路：
#   1. https://www.joinquant.com/post/72193  — 实战验证，9个月40%收益
#   2. https://www.joinquant.com/post/60824  — 核心创新：ATR动态调整回看期
#   3. https://www.joinquant.com/post/42673  — 核心资产轮动框架
#
# 策略核心：在12只跨资产ETF中，每日选出动量评分最高的1只全仓持有
# 评分公式：score = 年化收益率 × R²（趋势强度 × 趋势可靠性）
# 风控机制：急跌保护（日跌>5%→评分归零）+ 异常过滤（score>6排除）
# ============================================================================
#
# ⚠️ 已知问题（源码未修复，供读者参考）：
#   1. 第67/106行使用了 math.exp 但未 import math，运行时会 NameError
#      → 建议改为 np.exp（已导入numpy）
#   2. FixedSlippage(0.001) 是绝对值0.001元/份，不是0.1%比例滑点
#      → 不同价格ETF滑点比例不一致（1元国债0.1% vs 5元纳指0.02%）
#      → 建议改用 PriceRelatedSlippage(0.002) 统一比例
#   3. 第70/109行加权R²中 np.mean(y) 是未加权均值，与加权回归不一致
#      → 严格应用 np.average(y, weights=weights)
#   4. 第75/114行急跌保护未检查 prices 长度，数据不足时可能越界
#      → 建议加 len(prices) >= 4 前置判断
#   5. 第140行 positions[etf] 对从未持有的标的会 KeyError
#      → 建议改用 positions.get(etf)，判断 is None or total_amount == 0
#   6. 第59行获取了 "high" 列但从未使用，属冗余请求
# ============================================================================

import numpy as np
import pandas as pd
import talib  # 聚宽预装的技术指标库，此处用于计算ATR（平均真实波幅）


def initialize(context):
    """聚宽策略入口函数，启动时调用一次。负责设置基准、费率、滑点、全局变量和定时任务。"""

    # ---- 基准与回测选项 ----
    set_benchmark('000300.XSHG')          # 以沪深300指数为业绩基准
    set_option('use_real_price', True)     # 【必开】使用真实价格，避免前复权未来函数偏差
    set_option("avoid_future_data", True)  # 防止回测中使用未来数据（默认已开启，显式声明更安全）

    # ---- 滑点设置 ----
    # FixedSlippage(0.001) 表示每份偏移0.001元（绝对值，非百分比）
    # ⚠️ 注意：这是绝对值滑点，不同价格的ETF滑点比例不同
    #   - 1元国债ETF → 0.1%滑点
    #   - 5元纳指ETF → 0.02%滑点
    set_slippage(FixedSlippage(0.001))

    # ---- 交易费率设置 ----
    # type='fund' 表示按基金费率（ETF属于基金）
    # ETF免印花税（open_tax=0, close_tax=0），佣金万二，最低1元
    set_order_cost(
        OrderCost(open_tax=0, close_tax=0, open_commission=0.0002, close_commission=0.0002, close_today_commission=0,
                  min_commission=1), type='fund')
    log.set_level('system', 'error')  # 只输出系统错误日志，减少噪音

    # ---- ETF候选池 ----
    # 跨四大资产类别，利用低相关性实现轮动效果：
    #   某类资产动量强时持有，弱时切换到其他类别
    g.etf_pool = [
        # 境外股指
        "513100.XSHG",  # 纳指ETF — 跟踪纳斯达克100
        "513520.XSHG",  # 日经ETF — 跟踪日经225
        "513030.XSHG",  # 德国ETF — 跟踪德国DAX
        # 商品
        "518880.XSHG",  # 黄金ETF
        "159980.XSHE",  # 有色ETF — 有色金属
        "159985.XSHE",  # 豆粕ETF — 农产品
        "501018.XSHG",  # 南方原油 — 原油
        # 债券
        "511090.XSHG",  # 30年国债ETF
        # 国内股指
        "513130.XSHG",  # 恒生科技
        "512890.XSHG",  # 红利低波
        '159915.XSHE',  # 创业板
        '510300.XSHG',  # 沪深300
    ]

    # ---- 回看期参数 ----
    g.m_days = 25       # 固定回看期天数（get_rank使用），约5个交易周
    g.auto_day = True   # True=使用get_rank2（ATR动态回看期），False=使用get_rank（固定回看期）
    g.min_days = 20     # 动态回看期下限（约4周）
    g.max_days = 60     # 动态回看期上限（约12周）
    g.drop = 0.95       # 最近三天跌幅

    # ---- 定时任务 ----
    # 每个交易日9:40执行trade函数（开盘后10分钟，避开集合竞价波动）
    run_daily(trade, '9:40')


def get_rank(etf_pool):
    """基于年化收益×R²打分的固定回看期动量轮动

    评分逻辑：
      1. 对每个ETF的近m_days日收盘价取对数，做加权线性回归
      2. 回归斜率 → 年化收益率（趋势方向与强度）
      3. 加权R² → 趋势可靠性（价格沿趋势线的紧密程度）
      4. score = 年化收益率 × R²（强趋势+高可靠性=高分）
      5. 急跌保护：近3天任一天跌幅>5%则评分归零
    """
    data = pd.DataFrame(index=etf_pool, columns=["annualized_returns", "r2", "score"])
    current_data = get_current_data()  # 聚宽API：获取当前时刻所有标的的实时数据

    for etf in etf_pool:
        # 获取过去m_days(25)天的日K线数据
        # ⚠️ "high"列获取后未使用，属冗余请求
        df = attribute_history(etf, g.m_days, "1d", ["close", "high"])

        # 将历史收盘价与当前最新价拼接，得到完整的价格序列
        # current_data[etf].last_price 是聚宽API获取的当前最新成交价
        prices = np.append(df["close"].values, current_data[etf].last_price)

        # ---- 加权对数线性回归 ----
        # 对价格取对数：使百分比变化率变为线性，便于线性回归估算收益率
        y = np.log(prices)
        # 时间序号作为自变量：0, 1, 2, ...
        x = np.arange(len(y))
        # 线性递增权重[1→2]：近期数据权重更大，强调近期趋势
        # 最远端权重1，最近端权重2，近期数据影响力是远期的2倍
        weights = np.linspace(1, 2, len(y))

        # 一阶加权最小二乘回归：拟合 log(price) = slope × t + intercept
        slope, intercept = np.polyfit(x, y, 1, w=weights)

        # 年化收益率 = e^(日斜率 × 250交易日) - 1
        # slope是对数价格的日变化率，乘以250得到年化，exp转回普通收益率
        data.loc[etf, "annualized_returns"] = math.exp(slope * 250) - 1

        # ---- 加权R²（决定系数）----
        # R²衡量价格沿趋势线排列的紧密程度：
        #   R²≈1 → 趋势明确，价格紧贴趋势线
        #   R²≈0 → 价格散乱，趋势不可靠
        ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)  # 加权残差平方和（回归拟合误差）
        # ⚠️ np.mean(y) 是未加权均值，与加权回归体系不一致
        # 严格应用 np.average(y, weights=weights) 计算加权均值
        ss_tot = np.sum(weights * (y - np.average(y, weights=weights)) ** 2)              # 加权总平方和（数据离散程度）
        data.loc[etf, "r2"] = 1 - ss_res / ss_tot if ss_tot else 0

        # ---- 核心评分公式 ----
        # score = 年化收益率 × R²
        # 高收益+高R² = 强且稳定的上升趋势 → 高分
        # 高收益+低R² = 波动大的上涨 → 降分
        # 负收益×R² = 下跌趋势 → 负分（后续被过滤）
        data.loc[etf, "score"] = data.loc[etf, "annualized_returns"] * data.loc[etf, "r2"]

        # ---- 急跌保护（Crash Protection）----
        # 检查最近3天中任意一天的日跌幅是否超过5%
        # 如果是，强制评分归零，排除该ETF，防止在暴跌中追入或持有
        # ⚠️ 未检查 prices 长度是否>=4，数据不足时可能越界
        if min(prices[-1] / prices[-2], prices[-2] / prices[-3], prices[-3] / prices[-4]) < g.drop:
            data.loc[etf, "score"] = 0

    # ---- 过滤与排序 ----
    # 0 < score：排除负分（下跌趋势）和零分（急跌保护触发）
    # score < 6：排除异常高分（年化500%+，可能是数据异常或停牌复牌）
    data = data.query("0 < score < 6").sort_values(by="score", ascending=False)
    return data.index.tolist()


def get_rank2(etf_pool):
    """基于ATR动态调整回看期的动量轮动

    与get_rank的区别：回看期不是固定的25天，而是根据ATR（平均真实波幅）动态调整。

    核心创新（来自聚宽文章60824）：
      - 计算短期ATR(20日)和长期ATR(60日)的比值
      - 比值高 → 短期波动剧烈 → 用短回看期(20天)快速响应变化
      - 比值低 → 短期波动平静 → 用长回看期(60天)捕捉慢趋势
      - 回看期范围：[min_days(20), max_days(60)]

    公式：lookback = min_days + (max_days - min_days) × (1 - min(0.9, short_atr/long_atr))

    示例：
      short_atr/long_atr = 0.0 → lookback = 20 + 40×1.0 = 60（极度平静，长周期）
      short_atr/long_atr = 0.5 → lookback = 20 + 40×0.5 = 40（波动适中）
      short_atr/long_atr ≥ 0.9 → lookback = 20 + 40×0.1 = 24（剧烈波动，短周期）
    """
    data = pd.DataFrame(index=etf_pool, columns=["annualized_returns", "r2", "score"])
    current_data = get_current_data()

    for etf in etf_pool:
        # 获取 max_days+10(70)天的数据
        # 多取10天作为ATR计算的预热期，确保指标有足够的历史数据
        df = attribute_history(etf, g.max_days + 10, "1d", ["close", "high", "low"])

        # ---- 数据质量检查 ----
        # 数据长度不足 或 缺失值过多 → 跳过该ETF，避免在数据不完整的标的上计算
        if len(df) < (g.max_days + 10) or df["low"].isna().sum() > g.max_days or df[
            "close"].isna().sum() > g.max_days or df["high"].isna().sum() > g.max_days:
            continue

        # ---- ATR动态回看期计算 ----
        # ATR(Average True Range)：衡量市场波动程度的指标
        # 值越大表示波动越剧烈，值越小表示市场越平静
        long_atr = talib.ATR(df["high"], df["low"], df["close"], timeperiod=g.max_days)   # 60日ATR（长期波动率）
        short_atr = talib.ATR(df["high"], df["low"], df["close"], timeperiod=g.min_days)  # 20日ATR（短期波动率）

        # 动态回看期公式：
        #   ratio = min(0.9, short_atr/long_atr)  — 上限0.9，确保回看期不低于约24天
        #   lookback = 20 + 40 × (1 - ratio)
        # ratio高(短期波动大) → (1-ratio)小 → lookback小 → 短回看期快速响应
        # ratio低(短期波动小) → (1-ratio)大 → lookback大 → 长回看期捕捉慢趋势
        lookback = int(g.min_days + (g.max_days - g.min_days) * (1 - min(0.9, short_atr[-1] / long_atr[-1])))

        # 拼接当前价后截取最近lookback天的数据
        prices = np.append(df["close"].values, current_data[etf].last_price)
        prices = prices[-lookback:]
        log.info(f"{etf} lookback days :{lookback}, {len(prices)}")

        # ---- 以下评分逻辑与get_rank完全相同，只是输入数据长度是动态的 ----

        # 加权对数线性回归
        y = np.log(prices)
        x = np.arange(len(y))
        weights = np.linspace(1, 2, len(y))

        slope, intercept = np.polyfit(x, y, 1, w=weights)
        # ⚠️ 同get_rank，math.exp 未导入
        data.loc[etf, "annualized_returns"] = math.exp(slope * 250) - 1

        # 加权R²
        ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
        # ⚠️ 同get_rank，np.mean(y) 应为 np.average(y, weights=weights)
        ss_tot = np.sum(weights * (y - np.average(y, weights=weights)) ** 2)
        data.loc[etf, "r2"] = 1 - ss_res / ss_tot if ss_tot else 0

        # 核心评分
        data.loc[etf, "score"] = data.loc[etf, "annualized_returns"] * data.loc[etf, "r2"]

        # 急跌保护
        # ⚠️ 同get_rank，未检查 prices 长度是否>=4
        if min(prices[-1] / prices[-2], prices[-2] / prices[-3], prices[-3] / prices[-4]) < g.drop:
            data.loc[etf, "score"] = 0

    # 过滤与排序（同get_rank）
    data = data.query("0 < score < 6").sort_values(by="score", ascending=False)
    return data.index.tolist()


def trade(context):
    """每日调仓函数：持有动量评分最高的1只ETF，全仓进出

    调仓逻辑：
      1. 根据g.auto_day选择评分方法，取排名最高的1只ETF
      2. 卖出当前持仓中不在目标列表的ETF
      3. 买入目标列表中尚未持有的ETF
    """
    target_num = 1  # 目标持仓数量：只持有1只ETF（集中持仓，典型轮动策略）

    # 根据auto_day选择评分方法
    if g.auto_day:
        target_list = get_rank2(g.etf_pool)[:target_num]  # ATR动态回看期评分
    else:
        target_list = get_rank(g.etf_pool)[:target_num]   # 固定回看期评分

    # ---- 卖出逻辑 ----
    # 遍历当前所有持仓，不在目标列表中的全部清仓
    for etf in list(context.portfolio.positions):
        if etf not in target_list:
            order_target_value(etf, 0)  # 将该ETF市值调至0，即全部卖出
            print('卖出' + str(etf))
        else:
            print('继续持有' + str(etf))

    # ---- 买入逻辑 ----
    hold_list = list(context.portfolio.positions)  # 当前持仓列表
    # ⚠️ 注意：聚宽中order_target_value是异步下单，卖出可能尚未成交
    #   此时positions中可能仍包含刚卖出的标的
    #   但由于target_num=1，卖出标的和买入标的不重叠，实际影响很小

    if len(hold_list) < target_num:
        # 每只新买入ETF分配的金额 = 可用现金 / 需要买入的数量
        value = context.portfolio.available_cash / (target_num - len(hold_list))
        for etf in target_list:
            # ⚠️ positions[etf] 对从未持有过的标的会 KeyError
            #   聚宽positions字典只包含当前有持仓的标的
            #   建议改用 positions.get(etf) 安全访问
            if context.portfolio.positions[etf].total_amount == 0:
                order_target_value(etf, value)  # 按目标市值买入
                print('买入' + str(etf))
