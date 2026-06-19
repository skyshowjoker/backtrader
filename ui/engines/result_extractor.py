"""结果提取模块 - 从 backtrader strategy/analyzers/observers 提取结构化数据

将 backtrader 回测结果转换为 Plotly 可直接使用的字典格式。
"""

import math
from datetime import datetime

import backtrader as bt
from backtrader.utils import num2date


def extract_all(strat, data_feeds, benchmark_name=None):
    """从回测结果中提取所有可视化数据

    Args:
        strat: cerebro.run()[0] 返回的策略实例
        data_feeds: dict, {data_name: pandas DataFrame} 原始数据引用
        benchmark_name: str, 基准数据名称（如 '000300'）

    Returns:
        dict, 包含以下键:
            nav_dates: list[str] 策略净值日期
            nav_values: list[float] 策略净值序列
            benchmark_dates: list[str] 基准净值日期
            benchmark_values: list[float] 基准净值序列
            signals: list[dict] 买卖信号
            underlying_dates: list[str] 标的价格日期
            underlying_prices: list[float] 标的收盘价
            underlying_name: str 标的名称
            metrics: dict 绩效指标
            trades: list[dict] 已平仓交易列表
    """
    result = {
        'nav_dates': [],
        'nav_values': [],
        'benchmark_dates': [],
        'benchmark_values': [],
        'signals': [],
        'underlying_dates': [],
        'underlying_prices': [],
        'underlying_name': '',
        'metrics': {},
        'trades': [],
    }

    # 1. 策略净值曲线
    nav_dates, nav_values = _extract_nav(strat)
    result['nav_dates'] = nav_dates
    result['nav_values'] = nav_values

    # 2. 基准净值曲线
    bench_dates, bench_values = _extract_benchmark_nav(strat, benchmark_name)
    result['benchmark_dates'] = bench_dates
    result['benchmark_values'] = bench_values

    # 3. 买卖信号
    result['signals'] = _extract_signals(strat)

    # 4. 标的价格曲线
    result['underlying_dates'], result['underlying_prices'], result['underlying_name'] = \
        _extract_underlying(strat, data_feeds)

    # 5. 绩效指标
    result['metrics'] = _extract_metrics(strat)

    # 6. 交易记录
    result['trades'] = _extract_trades(strat)

    return result


def _extract_nav(strat):
    """提取策略净值曲线

    使用 TimeReturn 分析器的日收益率累乘计算净值。
    """
    try:
        time_return = strat.analyzers.time_return.get_analysis()
        if not time_return:
            return [], []

        dates = []
        nav = [1.0]  # 起始净值为 1.0

        for dt, r in time_return.items():
            dt_str = _format_date(dt)
            dates.append(dt_str)
            nav.append(nav[-1] * (1 + r))

        # nav[0] = 1.0 对应回测开始前，从 dates[0] 开始对应 nav[1]
        nav = nav[1:]

        return dates, nav
    except Exception as e:
        print(f"提取策略净值失败: {e}")
        return [], []


def _extract_benchmark_nav(strat, benchmark_name=None):
    """提取基准净值曲线

    使用 benchmark_return 分析器的日收益率累乘计算净值。
    """
    try:
        if not hasattr(strat.analyzers, 'benchmark_return'):
            return [], []

        bench_return = strat.analyzers.benchmark_return.get_analysis()
        if not bench_return:
            return [], []

        dates = []
        nav = [1.0]

        for dt, r in bench_return.items():
            dt_str = _format_date(dt)
            dates.append(dt_str)
            nav.append(nav[-1] * (1 + r))

        nav = nav[1:]

        return dates, nav
    except Exception as e:
        print(f"提取基准净值失败: {e}")
        return [], []


def _extract_signals(strat):
    """提取买卖信号

    从 strat._orders 提取所有已完成的买入/卖出订单。
    """
    signals = []
    try:
        for order in strat._orders:
            if order.status != order.Completed:
                continue
            if not order.executed.size:
                continue

            dt = num2date(order.executed.dt)
            signal = {
                'date': dt.strftime('%Y-%m-%d'),
                'price': round(order.executed.price, 3),
                'type': 'buy' if order.isbuy() else 'sell',
                'data_name': order.data._name if hasattr(order.data, '_name') else '',
                'size': order.executed.size,
            }
            signals.append(signal)

        # 按日期排序
        signals.sort(key=lambda x: x['date'])

    except Exception as e:
        print(f"提取信号失败: {e}")

    return signals


def _extract_underlying(strat, data_feeds):
    """提取标的价格曲线

    从原始 pandas DataFrame 中提取第一个数据源的收盘价。
    """
    if not data_feeds:
        return [], [], ''

    # 取第一个数据源作为标的
    first_name = list(data_feeds.keys())[0]
    df = data_feeds[first_name]

    if df is None or df.empty:
        return [], [], first_name

    dates = [d.strftime('%Y-%m-%d') for d in df.index]
    prices = df['close'].tolist()

    return dates, prices, first_name


def _extract_metrics(strat):
    """提取绩效指标

    从各 analyzer 提取结构化的指标字典。
    """
    metrics = {
        'total_return': 0.0,
        'annual_return': 0.0,
        'sharpe_ratio': None,
        'max_drawdown': 0.0,
        'max_drawdown_duration': 0,
        'total_trades': 0,
        'won_trades': 0,
        'lost_trades': 0,
        'win_rate': 0.0,
        'profit_factor': None,
        'avg_win': 0.0,
        'avg_loss': 0.0,
        'avg_trade_duration': 0,
    }

    # 总收益率 & 年化收益率
    try:
        returns = strat.analyzers.returns.get_analysis()
        metrics['total_return'] = (math.exp(returns.get('rtot', 0)) - 1) * 100
        metrics['annual_return'] = returns.get('rnorm100', 0)
    except Exception:
        pass

    # 夏普比率
    try:
        sharpe = strat.analyzers.sharpe.get_analysis()
        sr = sharpe.get('sharperatio', None)
        # 过滤异常值（低波动时 Sharpe 可能极大）
        if sr is not None and abs(sr) < 1000:
            metrics['sharpe_ratio'] = sr
        else:
            metrics['sharpe_ratio'] = None
    except Exception:
        pass

    # 最大回撤
    try:
        dd = strat.analyzers.drawdown.get_analysis()
        metrics['max_drawdown'] = dd.max.drawdown
        metrics['max_drawdown_duration'] = dd.max.len
    except Exception:
        pass

    # 交易统计
    try:
        trades = strat.analyzers.trades.get_analysis()
        total = trades.get('total', {}).get('total', 0)
        won = trades.get('won', {}).get('total', 0)
        lost = trades.get('lost', {}).get('total', 0)

        metrics['total_trades'] = total
        metrics['won_trades'] = won
        metrics['lost_trades'] = lost
        metrics['win_rate'] = round(won / total * 100, 1) if total > 0 else 0

        avg_win = trades.get('won', {}).get('pnl', {}).get('average', 0)
        avg_loss = trades.get('lost', {}).get('pnl', {}).get('average', 0)
        metrics['avg_win'] = avg_win
        metrics['avg_loss'] = avg_loss

        if avg_loss != 0:
            metrics['profit_factor'] = round(abs(avg_win / avg_loss), 2)

        # 平均持仓天数
        avg_len = trades.get('len', {}).get('average', 0)
        metrics['avg_trade_duration'] = avg_len

    except Exception:
        pass

    return metrics


def _extract_trades(strat):
    """提取已平仓交易列表

    从 TradeAnalyzer 提取详细的交易记录。
    注意：TradeAnalyzer 不提供逐笔明细，需要从 _tradespending 提取。
    """
    trades_list = []
    try:
        for trade in strat._tradespending:
            if not trade.isclosed:
                continue

            entry_dt = num2date(trade.dtopen) if trade.dtopen else None
            exit_dt = num2date(trade.dtclose) if trade.dtclose else None

            trades_list.append({
                'data_name': trade.data._name if hasattr(trade.data, '_name') else '',
                'direction': 'Long' if trade.size > 0 else 'Short',
                'entry_date': entry_dt.strftime('%Y-%m-%d') if entry_dt else '',
                'exit_date': exit_dt.strftime('%Y-%m-%d') if exit_dt else '',
                'entry_price': round(trade.price, 3),
                'exit_price': round(trade.pnlcomm / trade.size + trade.price, 3) if trade.size else 0,
                'size': abs(trade.size),
                'gross_pnl': round(trade.pnl, 2),
                'net_pnl': round(trade.pnlcomm, 2),
                'duration': trade.barlen,
            })

        trades_list.sort(key=lambda x: x['exit_date'], reverse=True)

    except Exception as e:
        print(f"提取交易记录失败: {e}")

    return trades_list


def _format_date(dt):
    """统一日期格式化"""
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d')
    try:
        return pd.Timestamp(dt).strftime('%Y-%m-%d')
    except Exception:
        return str(dt)
