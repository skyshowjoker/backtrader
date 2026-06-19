"""
ETF动量轮动策略 - Backtrader回测版
原始策略来源：聚宽 https://www.joinquant.com/post/72193
核心逻辑：基于年化收益×R²打分的动量轮动，支持ATR动态调整回看期

使用方法：
    python strategies/etf/etf_backtest.py

数据来源：akshare（自动下载A股ETF历史数据）
"""

import math
import datetime
import os
import numpy as np
import pandas as pd
import backtrader as bt
import akshare as ak
import talib

# 禁用系统代理，避免akshare请求被拦截
for proxy_key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(proxy_key, None)
os.environ['NO_PROXY'] = '*'


# ======================== 策略参数配置 ========================
ETF_POOL = {
    # 境外
    "513100": "纳指ETF",
    "513520": "日经ETF",
    "513030": "德国ETF",
    # 商品
    "518880": "黄金ETF",
    "159980": "有色ETF",
    "159985": "豆粕ETF",
    "501018": "南方原油",
    # 债券
    "511090": "30年国债ETF",
    # 国内
    "513130": "恒生科技",
    "512890": "红利低波",
    "159915": "创业板",
    "510300": "沪深300",
}

# 动量计算参数
AUTO_LOOKBACK = True       # 启用ATR动态回看期
FIXED_LOOKBACK = 25        # 固定回看期天数
MIN_LOOKBACK = 20          # 动态回看期下限
MAX_LOOKBACK = 60          # 动态回看期上限

# 持仓参数
TARGET_NUM = 1             # 持有得分最高的N只ETF

# 佣金和滑点
COMMISSION = 0.0002        # 买卖佣金率
SLIPPAGE = 0.001           # 滑点率

# 回测区间
FROM_DATE = datetime.datetime(2020, 1, 1)
TO_DATE = datetime.datetime(2025, 12, 31)
INITIAL_CASH = 1000000.0   # 初始资金100万
# ======================== 参数配置结束 ========================


def download_etf_data(code, start_date, end_date):
    """下载ETF历史数据，优先akshare，失败则用腾讯接口

    Args:
        code: ETF代码（纯数字，如 '513100'）
        start_date: 开始日期 'YYYYMMDD'
        end_date: 结束日期 'YYYYMMDD'

    Returns:
        DataFrame with columns: date, open, high, low, close, volume
    """
    # 方式1: akshare (东方财富源)
    try:
        df = ak.fund_etf_hist_em(symbol=code, period="daily",
                                  start_date=start_date, end_date=end_date, adjust="qfq")
        if df is not None and not df.empty:
            df = df.rename(columns={
                '日期': 'date', '开盘': 'open', '最高': 'high',
                '最低': 'low', '收盘': 'close', '成交量': 'volume',
            })
            df = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=['close'])
            print(f"  [OK-akshare] {code} {len(df)} bars ({df.index[0].date()} ~ {df.index[-1].date()})")
            return df
    except Exception as e:
        print(f"  [akshare fail] {code}: {e}")

    # 方式2: 腾讯财经接口 (直接HTTP请求)
    try:
        return _download_from_qq(code, start_date, end_date)
    except Exception as e:
        print(f"  [FAIL] {code} all sources failed: {e}")
        return None


def _download_from_qq(code, start_date, end_date):
    """通过腾讯财经接口下载ETF历史数据

    Args:
        code: ETF代码（纯数字）
        start_date: 开始日期 'YYYYMMDD'
        end_date: 结束日期 'YYYYMMDD'
    """
    import requests as _requests

    # 确定市场前缀：6开头为上海(sh)，其他为深圳(sz)
    market = 'sh' if code.startswith(('5', '6')) else 'sz'
    symbol = f"{market}{code}"

    # 腾讯接口最多返回800条数据，分批获取
    all_data = []
    end_dt = pd.to_datetime(end_date)
    start_dt = pd.to_datetime(start_date)

    session = _requests.Session()
    session.trust_env = False

    # 计算需要多少条数据（大约）
    days_diff = (end_dt - start_dt).days
    batch_size = 800
    batches = max(1, (days_diff // 250) + 1)

    current_end = end_dt.strftime('%Y-%m-%d')

    for i in range(batches + 1):
        url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
               f"?param={symbol},day,,{current_end},{batch_size},qfq")
        resp = session.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        data = resp.json()

        if data.get('code') != 0:
            break

        # 解析数据
        stock_data = data.get('data', {}).get(symbol, {})
        klines = stock_data.get('qfqday', stock_data.get('day', []))

        if not klines:
            break

        for k in klines:
            # 格式: [date, open, close, high, low, volume]
            d = pd.to_datetime(k[0])
            if start_dt <= d <= end_dt:
                all_data.append({
                    'date': d,
                    'open': float(k[1]),
                    'close': float(k[2]),
                    'high': float(k[3]),
                    'low': float(k[4]),
                    'volume': float(k[5]),
                })

        # 检查最早日期是否已覆盖起始日期
        earliest = pd.to_datetime(klines[0][0])
        if earliest <= start_dt:
            break

        # 下一批用最早日期作为结束
        current_end = earliest.strftime('%Y-%m-%d')

    if not all_data:
        print(f"  [WARN] {code} no data from QQ")
        return None

    df = pd.DataFrame(all_data)
    df = df.drop_duplicates(subset='date').set_index('date').sort_index()
    df = df.dropna(subset=['close'])

    print(f"  [OK-qq] {code} {len(df)} bars ({df.index[0].date()} ~ {df.index[-1].date()})")
    return df


def calc_momentum_score(prices):
    """计算动量得分 = 年化收益率 × R²

    使用加权线性回归（权重从1线性递增到2，近期权重大），
    斜率转换为年化收益率，R²衡量趋势可靠性。

    Args:
        prices: numpy array of close prices

    Returns:
        float: 动量得分（0表示不合格）
    """
    if len(prices) < 4:
        return 0.0

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
    if min(prices[-1] / prices[-2],
           prices[-2] / prices[-3],
           prices[-3] / prices[-4]) < 0.95:
        score = 0

    return score


def calc_atr_lookback(highs, lows, closes, min_days=MIN_LOOKBACK, max_days=MAX_LOOKBACK):
    """基于ATR动态调整回看期

    短期ATR/长期ATR比值越小（波动收敛），回看期越长；
    比值越大（波动放大），回看期越短。

    Args:
        highs, lows, closes: numpy arrays
        min_days: 最小回看期
        max_days: 最大回看期

    Returns:
        int: 动态回看期天数
    """
    if len(closes) < max_days + 10:
        return min_days

    long_atr = talib.ATR(highs, lows, closes, timeperiod=max_days)
    short_atr = talib.ATR(highs, lows, closes, timeperiod=min_days)

    if np.isnan(long_atr[-1]) or np.isnan(short_atr[-1]) or long_atr[-1] == 0:
        return min_days

    lookback = int(min_days + (max_days - min_days) * (1 - min(0.9, short_atr[-1] / long_atr[-1])))
    return max(min_days, min(max_days, lookback))


class ETFRotateStrategy(bt.Strategy):
    """ETF动量轮动策略

    核心逻辑：
    1. 每个交易日计算ETF池中所有ETF的动量得分
    2. 得分 = 年化收益率 * R^2（加权线性回归）
    3. 支持ATR动态调整回看期
    4. 持有得分最高的N只ETF，等权分配
    5. 近3日跌幅超5%的标的得分为0（动量崩溃保护）
    """

    params = (
        ('target_num', TARGET_NUM),
        ('auto_lookback', AUTO_LOOKBACK),
        ('fixed_lookback', FIXED_LOOKBACK),
        ('min_lookback', MIN_LOOKBACK),
        ('max_lookback', MAX_LOOKBACK),
        ('printlog', False),
    )

    def __init__(self):
        self.orders = {}  # data._name -> pending order
        self.last_rebalance_day = None
        self.datas_list = list(self.datas)

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'[{dt}] {txt}')

    def notify_order(self, order):
        name = order.data._name
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXEC: {name} '
                         f'price:{order.executed.price:.3f} '
                         f'size:{order.executed.size:.0f} '
                         f'cost:{order.executed.value:.2f}')
            else:
                self.log(f'SELL EXEC: {name} '
                         f'price:{order.executed.price:.3f} '
                         f'size:{order.executed.size:.0f}')

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'Order FAIL: {name} status={order.status} '
                     f'created_size={order.created.size:.0f} '
                     f'created_price={order.created.price:.3f} '
                     f'cash={self.broker.getcash():.0f} ')

        # Remove from pending
        self.orders.pop(name, None)

    def notify_trade(self, trade):
        if trade.isclosed:
            self.log(f'Trade PnL: {trade.data._name} gross:{trade.pnl:.2f} net:{trade.pnlcomm:.2f}')

    def prenext(self):
        """数据不足时也运行（有些ETF上市时间晚）"""
        self._rebalance()

    def next(self):
        """每日调仓逻辑"""
        self._rebalance()

    def _get_active_datas(self):
        """获取当前有足够数据的ETF列表

        在prenext阶段，有些ETF可能还没有数据（上市晚），
        需要跳过这些ETF，只对有足够数据的ETF计算得分。
        """
        min_data_len = 5  # 至少5天数据才能访问close[0]
        active = []
        for data in self.datas_list:
            if len(data) >= min_data_len:
                active.append(data)
        return active

    def get_score(self, data):
        """计算单个ETF的动量得分"""
        lookback = self.p.max_lookback + 15 if self.p.auto_lookback else self.p.fixed_lookback
        min_len = lookback + 1

        if len(data) < min_len:
            return 0.0

        closes = np.array(data.close.get(size=min_len))
        highs = np.array(data.high.get(size=min_len))
        lows = np.array(data.low.get(size=min_len))

        if self.p.auto_lookback:
            actual_lookback = calc_atr_lookback(
                highs, lows, closes,
                self.p.min_lookback, self.p.max_lookback
            )
        else:
            actual_lookback = self.p.fixed_lookback

        prices = closes[-(actual_lookback + 1):]
        return calc_momentum_score(prices)

    def _rebalance(self):
        """核心调仓逻辑 - 串行执行，每bar只做一个操作"""
        # 如果有pending orders，等待它们完成
        if self.orders:
            return

        current_date = self.datas[0].datetime.date(0)

        # 获取有数据的ETF
        active_datas = self._get_active_datas()
        if not active_datas:
            return

        # 计算所有活跃ETF的动量得分
        scores = {}
        for data in active_datas:
            scores[data._name] = self.get_score(data)

        # 过滤并排序：0 < score < 6
        valid_scores = {k: v for k, v in scores.items() if 0 < v < 6}

        if valid_scores:
            ranked = sorted(valid_scores.items(), key=lambda x: x[1], reverse=True)
            target_names = set(r[0] for r in ranked[:self.p.target_num])
        else:
            target_names = set()

        # 打印排名（每20天打印一次）
        if valid_scores and len(self) % 20 == 0:
            rank_str = ' | '.join([f'{name}({score:.3f})' for name, score in ranked[:5]])
            self.log(f'Rank: {rank_str}')

        # Step 1: 找到需要卖出的持仓（不在目标列表中）
        for data in active_datas:
            pos = self.getposition(data)
            if pos.size > 0 and data._name not in target_names:
                self.log(f'SELL {data._name} (score:{scores.get(data._name, 0):.3f})')
                order = self.close(data)
                if order:
                    self.orders[data._name] = order
                return  # 每bar只做一个操作

        # Step 2: 买入目标标的
        if not target_names:
            return

        total_value = self.broker.getvalue()
        # 留出2%余量给佣金和滑点，避免因资金不足被reject
        target_value_per = total_value * 0.98 / self.p.target_num

        for data in active_datas:
            if data._name not in target_names:
                continue
            pos = self.getposition(data)

            if pos.size == 0:
                self.log(f'BUY {data._name} (score:{scores.get(data._name, 0):.3f})')
                order = self.order_target_value(data, target_value_per)
                if order:
                    self.orders[data._name] = order
                return  # 每bar只做一个操作

        self.last_rebalance_day = current_date

    def _close_all(self, active_datas=None):
        """清仓所有持仓"""
        datas = active_datas or self.datas_list
        for data in datas:
            pos = self.getposition(data)
            if pos.size > 0:
                if data._name in self.orders:
                    self.cancel(self.orders[data._name])
                    self.orders.pop(data._name, None)
                order = self.close(data)
                if order:
                    self.orders[data._name] = order


class PandasDataETFFeed(bt.feeds.PandasData):
    """自定义PandasData，适配akshare数据格式"""
    params = (
        ('datetime', None),
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', -1),
    )


def run_backtest():
    """运行回测主函数"""
    print("=" * 60)
    print("ETF动量轮动策略 - Backtrader回测")
    print("=" * 60)
    print(f"回测区间: {FROM_DATE.date()} ~ {TO_DATE.date()}")
    print(f"初始资金: {INITIAL_CASH:,.0f}")
    print(f"ETF池: {len(ETF_POOL)} 只")
    print(f"动态回看期: {'开' if AUTO_LOOKBACK else '关'}"
          f"({MIN_LOOKBACK}~{MAX_LOOKBACK})" if AUTO_LOOKBACK else
          f"固定回看期: {FIXED_LOOKBACK}")
    print(f"持有数量: {TARGET_NUM}")
    print()

    # ========== 1. 下载数据 ==========
    print(">>> 下载ETF历史数据...")
    start_str = FROM_DATE.strftime('%Y%m%d')
    end_str = TO_DATE.strftime('%Y%m%d')

    data_feeds = {}
    for code, name in ETF_POOL.items():
        df = download_etf_data(code, start_str, end_str)
        if df is not None and len(df) > 60:  # 至少60天数据
            data_feeds[code] = df

    if not data_feeds:
        print("[ERROR] no ETF data downloaded, exit")
        return

    print(f"\n成功获取 {len(data_feeds)}/{len(ETF_POOL)} 只ETF数据\n")

    # ========== 2. 创建Cerebro引擎 ==========
    cerebro = bt.Cerebro()

    # cheat-on-close: 使用当日收盘价执行订单（模拟收盘前下单）
    cerebro.broker.set_coc(True)

    # 添加数据源
    for code, df in data_feeds.items():
        feed = PandasDataETFFeed(dataname=df, name=code)
        cerebro.adddata(feed, name=code)

    # 添加策略
    cerebro.addstrategy(ETFRotateStrategy)

    # 设置初始资金
    cerebro.broker.setcash(INITIAL_CASH)

    # 设置佣金（ETF基金费率，免印花税）
    cerebro.broker.setcommission(commission=COMMISSION)

    # 设置滑点
    cerebro.broker.set_slippage_perc(SLIPPAGE)

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe',
                        riskfreerate=0.02, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='time_return')
    cerebro.addanalyzer(bt.analyzers.PyFolio, _name='pyfolio')

    # ========== 3. 运行回测 ==========
    print(">>> 运行回测...")
    print("-" * 60)

    results = cerebro.run()
    strat = results[0]

    # ========== 4. 输出结果 ==========
    print()
    print("=" * 60)
    print("回测结果")
    print("=" * 60)

    final_value = cerebro.broker.getvalue()
    total_return = (final_value - INITIAL_CASH) / INITIAL_CASH * 100

    print(f"初始资金:   {INITIAL_CASH:>12,.2f}")
    print(f"最终资金:   {final_value:>12,.2f}")
    print(f"总收益率:   {total_return:>11.2f}%")

    # 夏普比率
    sharpe = strat.analyzers.sharpe.get_analysis()
    sharpe_ratio = sharpe.get('sharperatio', None)
    if sharpe_ratio is not None:
        print(f"夏普比率:   {sharpe_ratio:>11.3f}")
    else:
        print(f"夏普比率:   N/A")

    # 最大回撤
    dd = strat.analyzers.drawdown.get_analysis()
    print(f"最大回撤:   {dd.max.drawdown:>11.2f}%")
    print(f"最大回撤期: {dd.max.len:>8} 天")

    # 年化收益率
    returns = strat.analyzers.returns.get_analysis()
    if 'rnorm100' in returns:
        print(f"年化收益率: {returns['rnorm100']:>10.2f}%")

    # 交易统计
    trades = strat.analyzers.trades.get_analysis()
    total_trades = trades.get('total', {}).get('total', 0)
    won_trades = trades.get('won', {}).get('total', 0)
    lost_trades = trades.get('lost', {}).get('total', 0)
    if total_trades > 0:
        win_rate = won_trades / total_trades * 100
        print(f"总交易次数: {total_trades:>8}")
        print(f"盈利次数:   {won_trades:>8}")
        print(f"亏损次数:   {lost_trades:>8}")
        print(f"胜率:       {win_rate:>10.1f}%")

        avg_win = trades.get('won', {}).get('pnl', {}).get('average', 0)
        avg_loss = trades.get('lost', {}).get('pnl', {}).get('average', 0)
        if avg_loss != 0:
            profit_factor = abs(avg_win / avg_loss)
            print(f"盈亏比:     {profit_factor:>10.2f}")

    print("=" * 60)

    # ========== 5. 绘制净值曲线 ==========
    try:
        # 获取每日收益率序列
        time_return = strat.analyzers.time_return.get_analysis()
        if time_return:
            # 构建净值曲线
            dates = list(time_return.keys())
            returns_list = list(time_return.values())

            # 计算累计净值
            nav = [1.0]
            for r in returns_list:
                nav.append(nav[-1] * (1 + r))

            # 打印年度收益
            print("\n年度收益:")
            yearly = {}
            for dt, r in time_return.items():
                year = dt.year if hasattr(dt, 'year') else pd.to_datetime(dt).year
                if year not in yearly:
                    yearly[year] = 1.0
                yearly[year] *= (1 + r)

            for year, val in sorted(yearly.items()):
                ret = (val - 1) * 100
                bar = '#' * int(abs(ret) / 2)
                sign = '+' if ret >= 0 else ''
                print(f"  {year}: {sign}{ret:>6.1f}% {bar}")

    except Exception as e:
        print(f"年度收益计算异常: {e}")

    # 绘图（保存为PNG文件）
    try:
        print("\n>>> 生成图表...")
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig = cerebro.plot(style='candlestick', volume=False,
                           title='ETF Momentum Rotation Backtest',
                           figsize=(16, 9), returnfig=True)[0][0]
        output_path = os.path.join(os.path.dirname(__file__), 'etf_backtest_result.png')
        fig.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"图表已保存: {output_path}")
        plt.close(fig)
    except Exception as e:
        print(f"绘图失败: {e}")

    return results


if __name__ == '__main__':
    run_backtest()
