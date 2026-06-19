"""回测运行引擎 - 构建 Cerebro、运行回测、异步执行

提供同步和异步两种回测执行方式：
- run_backtest(): 同步执行，直接返回结果
- start_backtest() / check_result(): 异步执行，后台线程 + 轮询
"""

import os
import uuid
import threading
import datetime

import backtrader as bt
import pandas as pd

from .data_fetcher import download_data, ETF_POOL, BENCHMARK_POOL
from .result_extractor import extract_all


class PandasDataFeed(bt.feeds.PandasData):
    """通用 Pandas 数据源，适配 akshare 数据格式"""
    params = (
        ('datetime', None),
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', -1),
    )


# ==================== 异步执行状态 ====================
_results_store = {}  # task_id -> {'status': 'running'|'done'|'error', 'data': ...}


def run_backtest(strategy_class, strategy_params, config):
    """同步执行回测

    Args:
        strategy_class: bt.Strategy 子类
        strategy_params: dict, 策略参数
        config: dict, 回测配置:
            - start_date: str 'YYYY-MM-DD'
            - end_date: str 'YYYY-MM-DD'
            - initial_cash: float
            - commission: float
            - benchmark: str 基准代码（如 '000300'）
            - data_codes: list[str] 数据代码列表
            - data_type: str 数据类型 'etf'|'index'|'stock'

    Returns:
        dict, 提取的结构化结果（来自 result_extractor）
    """
    start_date = config.get('start_date', '2020-01-01')
    end_date = config.get('end_date', '2025-12-31')
    initial_cash = config.get('initial_cash', 1000000.0)
    commission = config.get('commission', 0.0002)
    benchmark_code = config.get('benchmark', '000300')
    data_codes = config.get('data_codes', [])
    data_type = config.get('data_type', 'etf')

    # 日期格式转换
    start_str = start_date.replace('-', '')
    end_str = end_date.replace('-', '')

    # 1. 下载数据
    data_feeds = {}
    for code in data_codes:
        df = download_data(code, start_str, end_str, data_type=data_type)
        if df is not None and len(df) > 20:
            data_feeds[code] = df

    if not data_feeds:
        raise ValueError("无法下载任何数据，请检查代码和日期范围")

    # 2. 下载基准数据
    benchmark_df = download_data(benchmark_code, start_str, end_str, data_type='index')
    benchmark_name = benchmark_code

    # 3. 创建 Cerebro
    cerebro = bt.Cerebro()

    # 添加数据源
    for code, df in data_feeds.items():
        feed = PandasDataFeed(dataname=df, name=code)
        cerebro.adddata(feed, name=code)

    # 添加基准数据（作为额外数据源，不影响策略逻辑）
    if benchmark_df is not None and len(benchmark_df) > 20:
        benchmark_feed = PandasDataFeed(dataname=benchmark_df, name=benchmark_code)
        cerebro.adddata(benchmark_feed, name=benchmark_code)

    # 添加策略
    cerebro.addstrategy(strategy_class, **strategy_params)

    # 设置资金
    cerebro.broker.setcash(initial_cash)

    # 设置佣金
    cerebro.broker.setcommission(commission=commission)

    # 4. 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe',
                        riskfreerate=0.02, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='time_return',
                        timeframe=bt.TimeFrame.Days)

    # 添加基准收益率分析器（跟踪基准数据的日收益率）
    if benchmark_df is not None and len(benchmark_df) > 20:
        cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='benchmark_return',
                            timeframe=bt.TimeFrame.Days, data=benchmark_feed)

    # 5. 运行回测
    results = cerebro.run()
    strat = results[0]

    # 6. 提取结果
    result = extract_all(strat, data_feeds, benchmark_name=benchmark_name)

    # 补充最终资产信息
    result['final_value'] = cerebro.broker.getvalue()
    result['initial_cash'] = initial_cash

    return result


# ==================== 异步执行 ====================

def start_backtest(strategy_class, strategy_params, config):
    """异步启动回测（后台线程）

    Args:
        strategy_class: bt.Strategy 子类
        strategy_params: dict, 策略参数
        config: dict, 回测配置

    Returns:
        str, task_id 用于轮询结果
    """
    task_id = str(uuid.uuid4())[:8]
    _results_store[task_id] = {'status': 'running', 'data': None}

    def _run():
        try:
            result = run_backtest(strategy_class, strategy_params, config)
            _results_store[task_id] = {'status': 'done', 'data': result}
        except Exception as e:
            _results_store[task_id] = {'status': 'error', 'data': str(e)}

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return task_id


def check_result(task_id):
    """检查异步回测结果

    Args:
        task_id: str, start_backtest 返回的任务 ID

    Returns:
        dict, {'status': 'running'|'done'|'error', 'data': ...}
    """
    return _results_store.get(task_id, {'status': 'unknown', 'data': None})


def clear_results():
    """清空所有回测结果"""
    _results_store.clear()
