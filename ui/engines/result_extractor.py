"""结果提取模块 - 从 backtrader strategy/analyzers/observers 提取结构化数据

将 backtrader 回测结果转换为 Plotly 可直接使用的字典格式。
"""

import math
from datetime import datetime

import backtrader as bt
import pandas as pd
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
            strategy_return_dates: list[str] 策略累计收益日期
            strategy_return_values: list[float] 策略累计收益百分比
            benchmark_dates: list[str] 基准净值日期
            benchmark_values: list[float] 基准净值序列
            benchmark_return_dates: list[str] 基准累计收益日期
            benchmark_return_values: list[float] 基准累计收益百分比
            excess_return_dates: list[str] 超额收益日期
            excess_return_values: list[float] 超额收益百分比
            underlying_series: list[dict] 多标的价格、归一价格与收益序列
            signals: list[dict] 买卖信号
            signal_analysis: dict 信号统计分析
            underlying_dates: list[str] 标的价格日期
            underlying_prices: list[float] 标的收盘价
            underlying_name: str 标的名称
            metrics: dict 绩效指标
            trades: list[dict] 已平仓交易列表
            positions: list[dict] 当前未平仓持仓
            orders: list[dict] 所有订单流水
            logs: list[dict] 策略/系统日志
    """
    result = {
        'partial': True,
        'progress': {
            'stage': 'loading',
        },
        'nav_dates': [],
        'nav_values': [],
        'strategy_return_dates': [],
        'strategy_return_values': [],
        'benchmark_dates': [],
        'benchmark_values': [],
        'benchmark_return_dates': [],
        'benchmark_return_values': [],
        'excess_return_dates': [],
        'excess_return_values': [],
        'underlying_series': [],
        'signals': [],
        'signal_analysis': {},
        'underlying_dates': [],
        'underlying_prices': [],
        'underlying_name': '',
        'metrics': {},
        'trades': [],
        'positions': [],
        'orders': [],
        'logs': [],
    }

    # 1. 策略净值曲线
    nav_dates, nav_values = _extract_nav(strat)
    result['nav_dates'] = nav_dates
    result['nav_values'] = nav_values
    result['strategy_return_dates'], result['strategy_return_values'] = \
        _nav_to_return(nav_dates, nav_values)

    # 2. 基准净值曲线
    bench_dates, bench_values = _extract_benchmark_nav(strat, benchmark_name)
    result['benchmark_dates'] = bench_dates
    result['benchmark_values'] = bench_values
    result['benchmark_return_dates'], result['benchmark_return_values'] = \
        _nav_to_return(bench_dates, bench_values)
    result['excess_return_dates'], result['excess_return_values'] = \
        _calc_excess_return(nav_dates, nav_values, bench_dates, bench_values)

    # 3. 买卖信号
    result['signals'] = _extract_signals(strat)
    result['signal_analysis'] = _build_signal_analysis(result['signals'])

    # 4. 标的价格和收益曲线
    result['underlying_series'] = _extract_underlying_series(data_feeds)
    result['underlying_dates'], result['underlying_prices'], result['underlying_name'] = \
        _extract_underlying(data_feeds)

    # 5. 绩效指标
    result['metrics'] = _extract_metrics(strat)

    # 6. 交易记录
    result['trades'] = _extract_trades(strat)
    result['positions'] = _extract_positions(strat)
    result['orders'] = _extract_orders(strat)

    return result


def build_partial_result(data_feeds=None, benchmark_df=None, benchmark_name=None):
    """构建数据加载阶段可渲染的部分结果。"""
    data_feeds = data_feeds or {}
    result = {
        'partial': True,
        'nav_dates': [],
        'nav_values': [],
        'strategy_return_dates': [],
        'strategy_return_values': [],
        'benchmark_dates': [],
        'benchmark_values': [],
        'benchmark_return_dates': [],
        'benchmark_return_values': [],
        'excess_return_dates': [],
        'excess_return_values': [],
        'underlying_series': _extract_underlying_series(data_feeds),
        'signals': [],
        'signal_analysis': _build_signal_analysis([]),
        'metrics': {},
        'trades': [],
        'positions': [],
        'orders': [],
        'logs': [],
    }

    result['underlying_dates'], result['underlying_prices'], result['underlying_name'] = \
        _extract_underlying(data_feeds)

    if benchmark_df is not None and not benchmark_df.empty:
        bench_dates, bench_values = _df_to_normalized_series(benchmark_df)
        result['benchmark_dates'] = bench_dates
        result['benchmark_values'] = bench_values
        result['benchmark_return_dates'], result['benchmark_return_values'] = \
            _nav_to_return(bench_dates, bench_values)
        result['benchmark_name'] = benchmark_name or ''

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


def _nav_to_return(dates, nav_values):
    """将净值序列转换为累计收益率百分比。"""
    if not dates or not nav_values:
        return [], []

    return dates, [round((value - 1.0) * 100, 4) for value in nav_values]


def _calc_excess_return(nav_dates, nav_values, bench_dates, bench_values):
    """计算策略相对基准的超额收益。"""
    if not nav_dates or not nav_values or not bench_dates or not bench_values:
        return [], []

    strategy = dict(zip(nav_dates, nav_values))
    benchmark = dict(zip(bench_dates, bench_values))
    dates = [date for date in nav_dates if date in benchmark]

    values = []
    for date in dates:
        bench = benchmark.get(date)
        if not bench:
            values.append(None)
            continue
        values.append(round((strategy[date] / bench - 1.0) * 100, 4))

    return dates, values


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


def _extract_underlying(data_feeds):
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


def _extract_underlying_series(data_feeds):
    """提取所有标的的价格、归一价格和累计收益序列。"""
    series = []
    if not data_feeds:
        return series

    for name, df in data_feeds.items():
        if df is None or df.empty or 'close' not in df:
            continue

        dates, normalized = _df_to_normalized_series(df)
        prices = [float(v) for v in df['close'].tolist()]
        returns = [round((value - 1.0) * 100, 4) for value in normalized]

        series.append({
            'name': name,
            'dates': dates,
            'prices': prices,
            'normalized': normalized,
            'returns': returns,
        })

    return series


def _df_to_normalized_series(df):
    """从 DataFrame 收盘价生成归一化净值序列。"""
    if df is None or df.empty or 'close' not in df:
        return [], []

    close = pd.to_numeric(df['close'], errors='coerce').dropna()
    if close.empty:
        return [], []

    first = float(close.iloc[0])
    if not first:
        return [], []

    dates = [_format_date(d) for d in close.index]
    values = [round(float(v) / first, 6) for v in close.tolist()]
    return dates, values


def _build_signal_analysis(signals):
    """构建信号可视化所需的聚合统计。"""
    by_symbol = {}
    by_date = {}
    total_buy = 0
    total_sell = 0

    for signal in signals or []:
        symbol = signal.get('data_name') or 'UNKNOWN'
        date = signal.get('date') or ''
        side = signal.get('type')

        by_symbol.setdefault(symbol, {'buy': 0, 'sell': 0, 'net': 0})
        by_date.setdefault(date, {'buy': 0, 'sell': 0, 'net': 0})

        if side == 'buy':
            total_buy += 1
            by_symbol[symbol]['buy'] += 1
            by_symbol[symbol]['net'] += 1
            by_date[date]['buy'] += 1
            by_date[date]['net'] += 1
        elif side == 'sell':
            total_sell += 1
            by_symbol[symbol]['sell'] += 1
            by_symbol[symbol]['net'] -= 1
            by_date[date]['sell'] += 1
            by_date[date]['net'] -= 1

    timeline = []
    exposure = 0
    for date in sorted(by_date):
        exposure += by_date[date]['net']
        timeline.append({
            'date': date,
            'buy': by_date[date]['buy'],
            'sell': by_date[date]['sell'],
            'net': by_date[date]['net'],
            'exposure': exposure,
        })

    symbols = []
    for symbol, stats in sorted(by_symbol.items()):
        symbols.append({
            'symbol': symbol,
            'buy': stats['buy'],
            'sell': stats['sell'],
            'net': stats['net'],
        })

    return {
        'total': total_buy + total_sell,
        'buy': total_buy,
        'sell': total_sell,
        'symbols': symbols,
        'timeline': timeline,
    }


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

    从策略内部交易集合提取逐笔明细。
    TradeAnalyzer 只提供聚合统计，逐笔价格需要结合 Trade/history。
    """
    trades_list = []
    try:
        for trade in _iter_closed_trades(strat):
            if not trade.isclosed:
                continue

            entry_dt = num2date(trade.dtopen) if trade.dtopen else None
            exit_dt = num2date(trade.dtclose) if trade.dtclose else None
            open_size = _get_trade_open_size(trade)
            is_long = _is_long_trade(trade, open_size)
            entry_price = _get_trade_entry_price(trade)
            exit_price = _get_trade_exit_price(trade, open_size, is_long)

            trades_list.append({
                'data_name': trade.data._name if hasattr(trade.data, '_name') else '',
                'direction': 'Long' if is_long else 'Short',
                'entry_date': entry_dt.strftime('%Y-%m-%d') if entry_dt else '',
                'exit_date': exit_dt.strftime('%Y-%m-%d') if exit_dt else '',
                'entry_price': round(entry_price, 3),
                'exit_price': round(exit_price, 3),
                'size': abs(open_size),
                'gross_pnl': round(trade.pnl, 2),
                'net_pnl': round(trade.pnlcomm, 2),
                'duration': trade.barlen,
            })

        trades_list.sort(key=lambda x: x['exit_date'], reverse=True)

    except Exception as e:
        print(f"提取交易记录失败: {e}")

    return trades_list


def _extract_positions(strat):
    """提取当前未平仓持仓。"""
    positions = []
    try:
        current_dt = _current_strategy_date(strat)
        for data in getattr(strat, 'datas', []) or []:
            pos = strat.getposition(data)
            if not pos or not pos.size:
                continue
            close = _safe_line_value(data.close)
            market_value = close * pos.size if close is not None else 0.0
            positions.append({
                'data_name': data._name if hasattr(data, '_name') else '',
                'direction': 'Long' if pos.size >= 0 else 'Short',
                'entry_date': '',
                'exit_date': '',
                'entry_price': round(float(pos.price or 0), 3),
                'exit_price': None,
                'last_price': round(float(close or 0), 3),
                'size': abs(pos.size),
                'gross_pnl': round(market_value - abs(pos.size) * float(pos.price or 0), 2),
                'net_pnl': round(market_value - abs(pos.size) * float(pos.price or 0), 2),
                'duration': '',
                'status': 'open',
                'as_of_date': current_dt,
                'market_value': round(market_value, 2),
            })
    except Exception as e:
        print(f"提取持仓失败: {e}")
    return positions


def _extract_orders(strat):
    """提取完整订单流水，包括未成交/取消订单。"""
    orders = []
    status_names = {
        getattr(bt.Order, 'Submitted', None): 'Submitted',
        getattr(bt.Order, 'Accepted', None): 'Accepted',
        getattr(bt.Order, 'Partial', None): 'Partial',
        getattr(bt.Order, 'Completed', None): 'Completed',
        getattr(bt.Order, 'Canceled', None): 'Canceled',
        getattr(bt.Order, 'Expired', None): 'Expired',
        getattr(bt.Order, 'Margin', None): 'Margin',
        getattr(bt.Order, 'Rejected', None): 'Rejected',
    }

    try:
        for order in getattr(strat, '_orders', []) or []:
            created_dt = _order_date(order.created.dt) if getattr(order, 'created', None) else ''
            executed_dt = _order_date(order.executed.dt) if getattr(order, 'executed', None) else ''
            orders.append({
                'ref': getattr(order, 'ref', ''),
                'date': executed_dt or created_dt,
                'created_date': created_dt,
                'executed_date': executed_dt,
                'data_name': order.data._name if hasattr(order.data, '_name') else '',
                'type': 'buy' if order.isbuy() else 'sell',
                'status': status_names.get(order.status, str(order.status)),
                'created_size': getattr(order.created, 'size', None),
                'executed_size': getattr(order.executed, 'size', None),
                'created_price': _round_or_none(getattr(order.created, 'price', None), 3),
                'executed_price': _round_or_none(getattr(order.executed, 'price', None), 3),
                'value': _round_or_none(getattr(order.executed, 'value', None), 2),
                'commission': _round_or_none(getattr(order.executed, 'comm', None), 2),
            })

        orders.sort(key=lambda item: (item.get('date') or '', item.get('ref') or 0), reverse=True)
    except Exception as e:
        print(f"提取订单流水失败: {e}")
    return orders


def _iter_closed_trades(strat):
    """遍历策略保存的所有已平仓交易，去重后返回。"""
    seen = set()

    trade_book = getattr(strat, '_trades', {}) or {}
    for data_trades in trade_book.values():
        for trade_list in data_trades.values():
            for trade in trade_list:
                ref = getattr(trade, 'ref', id(trade))
                if ref in seen or not getattr(trade, 'isclosed', False):
                    continue
                seen.add(ref)
                yield trade

    # 兼容旧结果对象：如果只有 pending 交易，也尽量提取
    for trade in getattr(strat, '_tradespending', []) or []:
        ref = getattr(trade, 'ref', id(trade))
        if ref in seen or not getattr(trade, 'isclosed', False):
            continue
        seen.add(ref)
        yield trade


def _get_trade_open_size(trade):
    """获取交易打开期间的最大持仓规模。"""
    history = getattr(trade, 'history', []) or []
    sizes = []
    for hist in history:
        try:
            sizes.append(hist.status.size)
        except Exception:
            pass

    if sizes:
        return max(sizes, key=lambda size: abs(size))

    return getattr(trade, 'size', 0) or 0


def _is_long_trade(trade, open_size):
    """判断交易方向。"""
    if hasattr(trade, 'long'):
        return bool(trade.long)
    return open_size >= 0


def _get_trade_entry_price(trade):
    """获取开仓均价。"""
    history = getattr(trade, 'history', []) or []
    for hist in history:
        try:
            if hist.status.size:
                return hist.status.price or hist.event.price
        except Exception:
            continue

    return getattr(trade, 'price', 0.0) or 0.0


def _get_trade_exit_price(trade, open_size, is_long):
    """获取平仓成交价，缺失时用盈亏反推。"""
    history = getattr(trade, 'history', []) or []
    for hist in reversed(history):
        try:
            if hist.status.size == 0 and hist.event.price:
                return hist.event.price
        except Exception:
            continue

    entry_price = getattr(trade, 'price', 0.0) or 0.0
    if open_size:
        pnl_per_unit = (getattr(trade, 'pnl', 0.0) or 0.0) / abs(open_size)
        return entry_price + pnl_per_unit if is_long else entry_price - pnl_per_unit

    return 0.0


def _format_date(dt):
    """统一日期格式化"""
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d')
    try:
        return pd.Timestamp(dt).strftime('%Y-%m-%d')
    except Exception:
        return str(dt)


def _safe_line_value(line):
    try:
        value = float(line[0])
    except Exception:
        return None
    if value != value:
        return None
    return value


def _round_or_none(value, digits):
    try:
        numeric = float(value)
    except Exception:
        return None
    if numeric != numeric:
        return None
    return round(numeric, digits)


def _order_date(value):
    try:
        return num2date(value).strftime('%Y-%m-%d')
    except Exception:
        return ''


def _current_strategy_date(strat):
    try:
        return strat.datas[0].datetime.date(0).strftime('%Y-%m-%d')
    except Exception:
        return ''
