# coding:gbk
"""
QMT ETF动量轮动策略

策略来源(聚宽):
  - https://www.joinquant.com/post/72193  实战跟踪9个月40%收益
  - https://www.joinquant.com/post/60824  基于历史波动率动态调整回溯期
  - https://www.joinquant.com/post/42673  ETF核心资产轮动

核心思路:
  对ETF池逐只计算 加权线性回归年化收益率 x R2 作为动量得分,
  持有得分最高的1只ETF, 每日调仓. 通过ATR动态调节回溯窗口,
  并以近3日急跌过滤规避动量崩溃.

ETF池(跨资产分散):
  境外(纳指/日经/德国) -> 商品(黄金/有色/豆粕/原油) -> 债券(30年国债) -> 国内(恒生科技/红利低波/创业板100)

因子流程(逐只ETF):
  收盘价 -> 取lookback天窗口 -> ln价格加权线性回归(权1->2)
  -> slope x 250 -> 年化收益率 = exp(slope*250) - 1
  -> 加权R2 = 1 - SS_res/SS_tot
  -> 得分 = 年化收益率 x R2
  -> 近3日任意相邻日跌幅>5% -> 得分清零
  -> 保留 0 < 得分 < 6 -> 降序排列取Top 1

ATR动态lookback:
  short_ATR / long_ATR 比值大 -> 波动加剧 -> 缩短回溯期(更关注近期趋势)
  short_ATR / long_ATR 比值小 -> 波动平稳 -> 延长回溯期(更远期趋势更可靠)

与母版架构差异:
  - 本策略是ETF轮动, 非截面因子选股, 不需要shift(1)信号矩阵
  - after_init仅预加载数据, handlebar中每日实时计算动量排名后直接交易
  - 无IPO/ST/市值中性化/行业中性化等截面处理(ETF不适用)
  - 无涨跌停判断(ETF无涨跌停限制)

容错:
  - init预定义所有信号变量, after_init异常不会导致handlebar崩溃
  - 数据缺失/不足时静默跳过该标的
  - passorder仅在QMT环境可用时调用(globals检测)
"""
import math
import numpy as np
import pandas as pd
import logging
from datetime import datetime, timedelta

# 配置 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('etf_momentum_rotate')

class G():
    pass

g = G()

# ============================================================================
#                              动量因子函数库
# ============================================================================

def calc_momentum_score(prices, lookback=None):
    """计算单只ETF动量得分 = 年化收益率 x R2

    对 ln(prices) 做加权一次多项式拟合(权从1线性增至2),
    slope对应日均对数收益, 年化后乘以拟合优度R2作为最终得分.
    R2越高说明趋势越干净, 低R2的震荡行情会被压低得分.

    Args:
        prices:  收盘价 np.array, 长度须 >= 4(3日跌幅检查+回归)
        lookback: 回溯天数, None则使用全部prices

    Returns:
        (score, annualized_return, r2)
        数据不足/异常时返回 (0, 0, 0)
    """
    if lookback is not None:
        prices = prices[-lookback:]

    n = len(prices)
    if n < 4:
        return 0, 0, 0

    # --- 急跌保护: 近3日任意相邻日跌幅超过5%则清零得分 ---
    try:
        min_ratio = min(prices[-1] / prices[-2],
                        prices[-2] / prices[-3],
                        prices[-3] / prices[-4])
        if min_ratio < 0.95:
            return 0, 0, 0
    except (ZeroDivisionError, IndexError):
        return 0, 0, 0

    # --- 加权线性回归 ---
    y = np.log(prices)
    x = np.arange(n)
    weights = np.linspace(1, 2, n)          # 近期权重更大, 降低远端噪声

    try:
        slope, intercept = np.polyfit(x, y, 1, w=weights)
    except (np.linalg.LinAlgError, ValueError):
        return 0, 0, 0

    # slope是日均对数收益, x250个交易日得年化对数收益, 再取指数减1
    annualized_return = math.exp(slope * 250) - 1

    # 加权R2: 衡量回归直线对价格走势的解释力
    y_pred = slope * x + intercept
    ss_res = np.sum(weights * (y - y_pred) ** 2)
    ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    score = annualized_return * r2
    return score, annualized_return, r2


def calc_dynamic_lookback(high_arr, low_arr, close_arr, min_days=20, max_days=60):
    """基于ATR动态调整回溯天数

    核心: 短期ATR / 长期ATR 比值反映近期波动相对强度
      - 比值大 -> 近期波动加剧 -> 缩短lookback(更关注近期趋势)
      - 比值小 -> 波动平稳 -> 延长lookback(远期趋势更可靠)
    比值上限截断至0.9, 防止极端值导致lookback过短.

    Args:
        high_arr / low_arr / close_arr: OHLC序列
        min_days: lookback下限
        max_days: lookback上限

    Returns:
        int, lookback天数
    """
    n = len(close_arr)
    if n < max_days + 10:
        return min_days

    # True Range = max(H-L, |H-prevC|, |L-prevC|)
    tr = np.maximum(
        high_arr[1:] - low_arr[1:],
        np.maximum(
            np.abs(high_arr[1:] - close_arr[:-1]),
            np.abs(low_arr[1:] - close_arr[:-1])
        )
    )

    long_atr = np.mean(tr[-max_days:])
    short_atr = np.mean(tr[-min_days:])

    if long_atr == 0:
        return max_days

    ratio = min(0.9, short_atr / long_atr)
    return int(min_days + (max_days - min_days) * (1 - ratio))


def rank_etf_pool(daily_close, daily_high, daily_low, etf_pool, target_date,
                  auto_day=True, m_days=25, min_days=20, max_days=60):
    """对ETF池计算动量排名

    遍历池中每只ETF, 截至target_date取历史价格,
    计算(可选动态lookback后的)动量得分, 过滤后按得分降序返回.

    Args:
        daily_close / daily_high / daily_low: 价格宽表 (index=日期, columns=代码)
        etf_pool:    ETF代码列表
        target_date: 截止日期 pd.Timestamp
        auto_day:    是否ATR动态调整lookback
        m_days:      固定lookback天数(auto_day=False时使用)
        min_days / max_days: 动态lookback范围

    Returns:
        list[str], 按得分降序排列的ETF代码(仅含 0 < score < 6 的标的)
    """
    scores = {}

    for etf in etf_pool:
        if etf not in daily_close.columns:
            continue

        if target_date not in daily_close.index:
            continue

        close_series = daily_close.loc[:target_date, etf].dropna()
        if len(close_series) < max_days + 10:
            logger.debug(f"  {etf} 数据不足 ({len(close_series)}天)")
            continue

        close_arr = close_series.values

        # 确定lookback
        if auto_day:
            high_series = daily_high.loc[:target_date, etf].dropna()
            low_series = daily_low.loc[:target_date, etf].dropna()
            min_len = min(len(close_arr), len(high_series), len(low_series))
            if min_len < max_days + 10:
                lookback = m_days
            else:
                lookback = calc_dynamic_lookback(
                    high_series.values[-min_len:],
                    low_series.values[-min_len:],
                    close_arr[-min_len:],
                    min_days=min_days, max_days=max_days
                )
        else:
            lookback = m_days

        score, ann_ret, r2 = calc_momentum_score(close_arr, lookback=lookback)

        if 0 < score < 6:
            scores[etf] = score
            logger.debug(f"  {etf}: lookback={lookback}, 年化={ann_ret:.4f}, R2={r2:.4f}, 得分={score:.4f}")
        else:
            logger.debug(f"  {etf}: 得分={score:.4f} (过滤)")

    ranked = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    if ranked:
        top3 = ', '.join(f"{e}({scores[e]:.3f})" for e in ranked[:3])
        logger.info(f"  [动量排名] Top3: {top3}")

    return ranked


# ============================================================================
#                              策略主体
# ============================================================================

def init(C):
    """策略初始化 - 设定回测区间/ETF池/策略参数/资金管理"""
    logger.info("=" * 50)
    logger.info("ETF动量轮动策略初始化")
    logger.info("=" * 50)

    # ------------------------回测参数设定-----------------------------
    g.start_date = '20230101'
    g.end_date = '20260615'
    g.backtest_start_time = '2023-01-01 00:00:00'
    g.backtest_end_time = '2026-06-15 00:00:00'
    g.period = '1d'

    # ------------------------ETF池设定-----------------------------
    # QMT代码格式: 代码.交易所 (SH=上海, SZ=深圳)
    g.etf_pool = [
        # 境外
        "513100.SH",   # 纳指ETF
        "513520.SH",   # 日经ETF
        "513030.SH",   # 德国ETF
        # 商品
        "518880.SH",   # 黄金ETF
        "159980.SZ",   # 有色ETF
        "159985.SZ",   # 豆粕ETF
        "501018.SH",   # 南方原油
        # 债券
        "511090.SH",   # 30年国债ETF
        # 国内
        "513130.SH",   # 恒生科技
        "512890.SH",   # 红利低波
        "159915.SZ",   # 创业板100
    ]

    # ------------------------策略参数-----------------------------
    g.target_num = 1           # 同时持有ETF数量
    g.m_days = 25              # 固定lookback天数(auto_day=False时生效)
    g.auto_day = True          # True=ATR动态调整lookback, False=固定m_days
    g.min_days = 20            # 动态lookback下限
    g.max_days = 60            # 动态lookback上限
    g.rebalance_days = 1       # 调仓频率(交易日), 1=每日调仓

    # ------------------------资金管理参数-----------------------------
    g.initial_capital = 1000000
    g.cash_usage_ratio = 0.98  # ETF流动性好, 资金利用率可设高
    g.accid = 'test'

    # ------------------------预定义信号变量(容错设计)-----------------------------
    # 防止after_init报错导致handlebar崩溃
    g.target_etf_list = []       # 每日目标ETF列表
    g.daily_close = pd.DataFrame()
    g.daily_high = pd.DataFrame()
    g.daily_low = pd.DataFrame()
    g.daily_open = pd.DataFrame()
    g.signal_ready = False       # 信号是否就绪

    # ------------------------变量初始化-----------------------------
    g.money = g.initial_capital
    g.holdings = {}
    g.trade_records = []
    g.trade_day_count = 0

    logger.info(f"参数设置: 回测区间 {g.start_date}~{g.end_date}")
    logger.info(f"ETF池: {len(g.etf_pool)} 只")
    logger.info(f"动量参数: lookback={g.m_days}, 自动调整={g.auto_day}, 范围=[{g.min_days},{g.max_days}]")
    logger.info(f"资金管理: 初始资金 {g.initial_capital:,}, 持有 {g.target_num} 只, 利用率 {g.cash_usage_ratio*100:.0f}%")
    logger.info("=" * 50)


def after_init(C):
    """预加载全区间行情数据

    一次性拉取所有ETF的OHLC日线, 存入g.daily_*宽表供handlebar按日切片.
    ETF标的少(11只), 每日实时计算动量排名开销可忽略,
    无需像截面选股策略那样在after_init预计算信号矩阵.

    数据获取策略(按优先级):
      1. 批量获取 + front复权
      2. 批量获取 + 不复权(fallback)
      3. 逐只获取 + 不复权(最终兜底)
    """
    logger.info("=" * 50)
    logger.info("数据获取与预加载")
    logger.info("=" * 50)

    # ==================== 1. 获取行情数据 ====================
    daily_data = None
    success = False

    # --- 策略1: 批量获取 + front复权 ---
    logger.info("策略1: 批量获取ETF日频数据(front复权)...")
    try:
        daily_data = C.get_market_data_ex(
            [], g.etf_pool, period='1d',
            start_time=g.start_date, end_time=g.end_date,
            dividend_type='front', fill_data=False
        )
        if daily_data and len(daily_data) > 0:
            logger.info(f"  批量获取成功, 返回 {len(daily_data)} 只ETF数据")
            success = True
        else:
            logger.warning("  批量获取(front)返回空数据")
    except Exception as e:
        logger.warning(f"  批量获取(front)异常: {e}")

    # --- 策略2: 批量获取 + 不复权 ---
    if not success:
        logger.info("策略2: 批量获取ETF日频数据(不复权)...")
        try:
            daily_data = C.get_market_data_ex(
                [], g.etf_pool, period='1d',
                start_time=g.start_date, end_time=g.end_date,
                dividend_type='none', fill_data=False
            )
            if daily_data and len(daily_data) > 0:
                logger.info(f"  批量获取(不复权)成功, 返回 {len(daily_data)} 只ETF数据")
                success = True
            else:
                logger.warning("  批量获取(不复权)返回空数据")
        except Exception as e:
            logger.warning(f"  批量获取(不复权)异常: {e}")

    # --- 策略3: 逐只获取(最终兜底) ---
    if not success:
        logger.info("策略3: 逐只获取ETF日频数据(兜底模式)...")
        daily_data = {}
        for etf in g.etf_pool:
            try:
                etf_data = C.get_market_data_ex(
                    [], [etf], period='1d',
                    start_time=g.start_date, end_time=g.end_date,
                    dividend_type='none', fill_data=False
                )
                if etf_data and etf in etf_data and not etf_data[etf].empty:
                    daily_data[etf] = etf_data[etf]
                    logger.info(f"  {etf}: 获取成功, {len(etf_data[etf])} 条数据")
                else:
                    logger.warning(f"  {etf}: 无数据")
            except Exception as e:
                logger.warning(f"  {etf}: 获取异常 - {e}")

        if len(daily_data) > 0:
            logger.info(f"  逐只获取成功 {len(daily_data)}/{len(g.etf_pool)} 只ETF")
            success = True
        else:
            logger.error("  逐只获取也失败!")

    # --- 最终检查 ---
    if not success or not daily_data:
        logger.error("行情数据获取失败! 策略将无法生成信号")
        logger.error("请检查: 1)QMT数据是否已下载 2)ETF代码是否正确 3)日期范围是否有数据")
        return

    daily_close_raw = get_df_ex(daily_data, "close")
    daily_open_raw = get_df_ex(daily_data, "open")
    daily_high_raw = get_df_ex(daily_data, "high")
    daily_low_raw = get_df_ex(daily_data, "low")
    daily_volume_raw = get_df_ex(daily_data, "volume")

    # 【容错】数据为空时提前返回
    if daily_close_raw.empty:
        logger.error("行情数据解析后为空! get_df_ex可能无法提取字段")
        logger.error(f"  daily_data keys: {list(daily_data.keys()) if daily_data else 'None'}")
        if daily_data:
            first_key = list(daily_data.keys())[0]
            first_df = daily_data[first_key]
            logger.error(f"  第一只ETF({first_key}) columns: {list(first_df.columns) if hasattr(first_df, 'columns') else 'N/A'}")
            logger.error(f"  第一只ETF({first_key}) shape: {first_df.shape if hasattr(first_df, 'shape') else 'N/A'}")
        return

    logger.info(f"获取到 {len(daily_close_raw)} 个交易日, {len(daily_close_raw.columns)} 只ETF")

    # ==================== 数据质量体检 ====================
    total_cells = daily_close_raw.size
    real_missing = daily_close_raw.isna().sum().sum()
    missing_ratio = (real_missing / total_cells) * 100 if total_cells > 0 else 0

    zero_vol_count = (daily_volume_raw == 0).sum().sum()
    zero_vol_ratio = (zero_vol_count / total_cells) * 100 if total_cells > 0 else 0

    if missing_ratio > 5:
        logger.error(f"[数据检查] 严重缺失! 空值比例: {missing_ratio:.2f}% ({real_missing}点)")
    elif missing_ratio > 0:
        logger.warning(f"[数据检查] 存在空值. 空值比例: {missing_ratio:.2f}% ({real_missing}点)")

    if zero_vol_ratio > 0:
        logger.info(f"[数据检查] 停牌统计. 比例: {zero_vol_ratio:.2f}% ({zero_vol_count}点)")

    # ==================== 索引转换与填充 ====================
    # 注意: 必须原地修改index后再赋值给g, 不能先赋值再改index(局部变量会断开引用)
    for df in [daily_close_raw, daily_open_raw, daily_high_raw, daily_low_raw]:
        if not df.empty:
            df.index = pd.to_datetime(df.index.astype(str))

    # 前向填充(ETF停牌时沿用前值)
    g.daily_close = daily_close_raw.ffill()
    g.daily_open = daily_open_raw.ffill()
    g.daily_high = daily_high_raw.ffill()
    g.daily_low = daily_low_raw.ffill()

    g.signal_ready = True

    # ==================== 打印最新调仓建议 ====================
    last_date = g.daily_close.index[-1]
    ranked = rank_etf_pool(
        g.daily_close, g.daily_high, g.daily_low,
        g.etf_pool, last_date,
        auto_day=g.auto_day, m_days=g.m_days,
        min_days=g.min_days, max_days=g.max_days
    )
    targets = ranked[:g.target_num]

    logger.info("*" * 30)
    logger.info(f"【最新调仓建议】 目标日期: {last_date.strftime('%Y-%m-%d')}")
    if targets:
        for i, etf in enumerate(targets):
            try:
                name = C.get_instrument_detail(etf).get('InstrumentName', '')
            except Exception:
                name = ''
            logger.info(f"  [{i+1}] {etf} ({name})")
    else:
        logger.warning("最新日期无合格ETF!")
    logger.info("*" * 30)

    logger.info("数据预加载完成, 策略信号就绪")
    logger.info("=" * 50)
def sync_from_qmt(accid):
    """从 QMT 同步持仓和资金"""
    try:
        positions = get_trade_detail_data(accid, 'stock', 'POSITION')
        g.holdings = {}
        for pos in positions:
            code = pos.m_strInstrumentID + "." + pos.m_strExchangeID
            g.holdings[code] = {"持仓数量": pos.m_nVolume}
        account = get_trade_detail_data(accid, 'stock', 'account')
        if account:
            g.money = account[0].m_dAvailable
        logger.info(f"[同步] 持仓 {len(g.holdings)} 只, 现金 {g.money:,.0f}")
    except Exception as e:
        logger.debug(f"QMT 同步跳过: {e}")


def handlebar(C):
    """每日交易执行

    流程:
      1. 调仓频率过滤(rebalance_days=1时每日都执行)
      2. 取当日日期, 计算截至当日的动量排名
      3. 无合格标的 -> 清仓观望
      4. 有标的 -> 先卖后买, 开盘价成交
    """
    g.trade_day_count += 1

    # 调仓频率控制
    if g.rebalance_days > 1 and g.trade_day_count % g.rebalance_days != 1:
        return

    # 【容错】信号未就绪时跳过(仅首次打印警告)
    if not g.signal_ready:
        if g.trade_day_count <= 3:
            logger.warning("信号未就绪(after_init数据获取可能失败), 跳过当日交易")
        return

    current_time_int = C.get_bar_timetag(C.barpos)
    current_date_ts = pd.to_datetime(timetag_to_datetime(current_time_int, "%Y%m%d"))
    current_date_str = current_date_ts.strftime('%Y-%m-%d')

    if current_date_ts not in g.daily_close.index:
        return

    # ==================== 计算当日动量排名 ====================
    logger.info(f">>> 调仓日 {current_date_str} (第{g.trade_day_count}个交易日)")

    ranked_etfs = rank_etf_pool(
        g.daily_close, g.daily_high, g.daily_low,
        g.etf_pool, current_date_ts,
        auto_day=g.auto_day, m_days=g.m_days,
        min_days=g.min_days, max_days=g.max_days
    )

    target_list = ranked_etfs[:g.target_num]
    g.target_etf_list = target_list

    if not target_list:
        logger.warning("无符合条件的ETF, 空仓观望")
        # 卖出所有持仓
        sell_all_holdings(C, current_date_ts)
        return

    logger.info(f"  目标ETF: {', '.join(target_list)}")

    # ==================== 执行交易 ====================
    sync_from_qmt(g.accid)

    # 卖出不在目标名单的持仓
    execute_sell(C, current_date_ts, target_list)

    # 买入目标ETF
    execute_buy(C, current_date_ts, target_list)

    print_holdings_summary(current_date_ts)


# ============================================================================
#                              交易执行函数
# ============================================================================

def sell_all_holdings(C, current_date_ts):
    """清仓全部持仓(无合格标的时触发)"""
    positions = get_holdings(g.accid, 'fund')
    if not positions:
        return

    for stock in list(positions.keys()):
        amount = positions[stock]['持仓数量']
        price = get_price_at_time(stock, current_date_ts)
        if price and price > 0 and amount > 0:
            sell_value = price * amount
            current_date_str = current_date_ts.strftime('%Y%m%d')

            if 'passorder' in globals():
                passorder(24, 1101, g.accid, stock, 11, float(price), float(amount), "backtest", 1, "清仓", C)

            g.money += sell_value
            if stock in g.holdings: del g.holdings[stock]

            g.trade_records.append({
                '日期': current_date_str, '股票代码': stock,
                '交易类型': '清仓', '价格': price, '数量': amount, '金额': sell_value
            })
            logger.info(f"  [清仓] {stock}, 价格: {price:.3f}, 数量: {amount}, 金额: {sell_value:,.0f}")


def execute_sell(C, current_date_ts, target_list):
    """卖出不在目标名单内的ETF"""
    positions = get_holdings(g.accid, 'fund')
    if not positions:
        logger.debug("当前无持仓, 跳过卖出")
        return

    current_date_str = current_date_ts.strftime('%Y%m%d')
    sell_count = 0
    sell_amount = 0
    sell_stocks = []

    for stock in list(positions.keys()):
        if stock not in target_list:
            amount = positions[stock]['持仓数量']
            price = get_price_at_time(stock, current_date_ts)

            if price and price > 0 and amount > 0:
                sell_value = price * amount

                if 'passorder' in globals():
                    passorder(24, 1101, g.accid, stock, 11, float(price), float(amount), "backtest", 1, "轮动卖出", C)

                g.money += sell_value
                if stock in g.holdings: del g.holdings[stock]

                sell_count += 1
                sell_amount += sell_value
                sell_stocks.append(stock.split('.')[0])

                g.trade_records.append({
                    '日期': current_date_str, '股票代码': stock,
                    '交易类型': '轮动卖出', '价格': price, '数量': amount, '金额': sell_value
                })
                logger.info(f"  [轮动卖出] {stock}, 价格: {price:.3f}, 数量: {amount}, 金额: {sell_value:,.0f}")
        else:
            logger.info(f"  [继续持有] {stock}")

    if sell_count > 0:
        stocks_str = ','.join(sell_stocks[:5]) + ('...' if len(sell_stocks) > 5 else '')
        logger.info(f"[卖出] {sell_count}只 ({stocks_str}), 回收: {sell_amount:,.0f}")


def execute_buy(C, current_date_ts, target_list):
    """等额买入目标ETF(不在持仓中的部分)"""
    positions = get_holdings(g.accid, 'fund')
    current_date_str = current_date_ts.strftime('%Y%m%d')

    # 找出需要新买入的ETF
    new_buy = [etf for etf in target_list if etf not in positions]
    if not new_buy:
        logger.info("  目标ETF已持有, 无需买入")
        return

    total_available = g.money
    if total_available <= 0:
        logger.warning("可用资金不足, 无法买入")
        return

    # ETF最小交易单位: 100份
    lot_size = 100
    budget_per_etf = (total_available * g.cash_usage_ratio) / len(new_buy)

    buy_count = 0
    buy_amount = 0
    buy_stocks = []

    for etf in new_buy:
        price = get_price_at_time(etf, current_date_ts)
        if not price or price <= 0:
            logger.warning(f"  {etf} 无法获取价格, 跳过买入")
            continue

        # 计算买入数量(100的整数倍)
        buy_volume = int((budget_per_etf / price) // lot_size) * lot_size

        if buy_volume < lot_size:
            logger.warning(f"  {etf} 资金不足买入1手, 跳过")
            continue

        if g.money < (price * buy_volume):
            logger.warning(f"  资金耗尽, 停止买入: {etf}")
            break

        cost = price * buy_volume

        if 'passorder' in globals():
            passorder(23, 1101, g.accid, etf, 11, price, buy_volume, "backtest", 1, "轮动买入", C)

        g.money -= cost
        g.holdings[etf] = {
            "持仓数量": buy_volume,
            "成本价": price,
            "买入日期": current_date_str
        }

        buy_count += 1
        buy_amount += cost
        buy_stocks.append(etf.split('.')[0])

        g.trade_records.append({
            '日期': current_date_str, '股票代码': etf,
            '交易类型': '轮动买入', '价格': price, '数量': buy_volume, '金额': cost
        })
        logger.info(f"  [轮动买入] {etf}, 价格: {price:.3f}, 数量: {buy_volume}, 金额: {cost:,.0f}")

    if buy_count > 0:
        stocks_str = ','.join(buy_stocks[:5]) + ('...' if len(buy_stocks) > 5 else '')
        logger.info(f"[买入] {buy_count}只 ({stocks_str}), 花费: {buy_amount:,.0f}, 剩余: {g.money:,.0f}")


def print_holdings_summary(current_date_ts):
    """打印持仓汇总"""
    positions = get_holdings(g.accid, 'fund')
    if not positions:
        logger.info(f"[持仓汇总] 空仓, 现金: {g.money:,.0f}")
        return

    total_mv = sum(
        (get_price_at_time(s, current_date_ts) or 0) * info['持仓数量']
        for s, info in positions.items()
    )

    try:
        available_cash = get_trade_detail_data(g.accid, 'stock', 'account')[0].m_dAvailable
    except Exception as e:
        logger.debug(f"获取 QMT 资金跳过: {e}")
        available_cash = g.money

    total_asset = total_mv + available_cash
    position_ratio = total_mv / total_asset * 100 if total_asset > 0 else 0

    hold_names = [s.split('.')[0] for s in positions]
    logger.info(f"[持仓汇总] 持仓: {','.join(hold_names)}, 市值: {total_mv:,.0f}, 现金: {available_cash:,.0f}, 总资产: {total_asset:,.0f}, 仓位: {position_ratio:.1f}%")


# ============================================================================
#                              辅助工具函数
# ============================================================================

def get_price_at_time(stock, current_date_ts):
    """获取指定时间的开盘价(用于回测成交价)"""
    if hasattr(g, 'daily_open') and stock in g.daily_open.columns:
        if current_date_ts in g.daily_open.index:
            price = g.daily_open.loc[current_date_ts, stock]
            if pd.notna(price) and price > 0:
                return price
    return None


def get_holdings(accid, datatype):
    """获取持仓信息"""
    PositionInfo_dict = {}
    try:
        resultlist = get_trade_detail_data(accid, datatype, 'POSITION')
        for obj in resultlist:
            stock_code = obj.m_strInstrumentID + "." + obj.m_strExchangeID
            PositionInfo_dict[stock_code] = {"持仓数量": obj.m_nVolume}
    except Exception as e:
        logger.debug(f"获取 QMT 持仓跳过: {e}, 使用本地记录")
        for stock, info in g.holdings.items():
            if isinstance(info, dict):
                volume = info.get('持仓数量', 0)
            else:
                volume = info
            if volume > 0:
                PositionInfo_dict[stock] = {"持仓数量": volume}
    return PositionInfo_dict


def get_df_ex(data, field):
    """从行情数据提取字段的宽表"""
    if not data:
        logger.debug(f"get_df_ex: data为空, field={field}")
        return pd.DataFrame()
    _columns = list(data.keys())
    if not _columns:
        logger.debug(f"get_df_ex: data无keys, field={field}")
        return pd.DataFrame()
    # 找到第一个有效DataFrame作为索引基准
    ref_df = None
    for s in _columns:
        if hasattr(data[s], 'index') and len(data[s]) > 0:
            ref_df = data[s]
            break
    if ref_df is None:
        logger.warning(f"get_df_ex: 所有ETF的{field}数据均为空")
        return pd.DataFrame()
    _index = ref_df.index
    df = pd.DataFrame(index=_index, columns=_columns)
    for s in _columns:
        try:
            if hasattr(data[s], 'columns') and field in data[s].columns:
                df[s] = data[s][field]
            elif hasattr(data[s], 'columns'):
                logger.debug(f"get_df_ex: {s} 无 {field} 字段, 可用字段: {list(data[s].columns)}")
        except Exception as e:
            logger.warning(f"get_df_ex: {s} 提取{field}异常: {e}")
    return df


def timetag_to_datetime(timetag, format_str="%Y%m%d%H%M%S"):
    """时间戳转日期字符串"""
    if timetag > 1000000000000: timetag = timetag // 1000
    return datetime.fromtimestamp(timetag).strftime(format_str)
