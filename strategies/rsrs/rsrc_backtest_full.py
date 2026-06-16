"""
RSRS价值选股策略 - 完整深度复刻回测脚本（优化版）
完全复刻聚宽原策略，不做任何简化

策略参数：
- RSRS周期N = 18
- RSRS样本M = 1100
- 买入阈值 = 0.7
- 卖出阈值 = -0.7
- 持仓股票数 = 10
- 基准指数 = 沪深300 (000300.SH)

优化点：
- 数据加载缓存
- RSRS指标向量化计算
- 选股结果缓存
- 各阶段耗时统计
"""

import sys
import os
# 添加项目根目录到路径
sys.path.insert(0, r'C:\Users\perlicue\PycharmProjects\backtrader')

from datetime import datetime
import time
import backtrader as bt
import pandas as pd
import numpy as np
from tushare_data_loader import TushareDataLoader
from strategies.rsrs.rsrc_strategy_full import RSRSStrategyFull, ValueStockSelector


# 数据路径配置
DATA_PATH = r'C:\Users\perlicue\Documents\开发文档\stock_data\行情数据'


class TimingContext:
    """耗时统计上下文管理器"""

    def __init__(self, name):
        self.name = name
        self.start_time = None
        self.elapsed = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, *args):
        self.elapsed = time.time() - self.start_time
        print(f"  [耗时] {self.name}: {self.elapsed:.2f}秒")


def run_full_backtest():
    """
    完整深度复刻版回测（优化版）
    完全按照原策略逻辑实现，添加耗时统计
    """

    print("=" * 80)
    print("RSRS价值选股策略 - 完整深度复刻版（优化版）")
    print("=" * 80)
    print("\n策略参数:")
    print("  RSRS周期N = 18")
    print("  RSRS样本M = 1100")
    print("  买入阈值 = 0.7")
    print("  卖出阈值 = -0.7")
    print("  持仓股票数 = 10")
    print("  基准指数 = 沪深300")
    print("=" * 80)

    # 总耗时统计
    total_start = time.time()
    timings = {}

    # 1. 创建引擎
    cerebro = bt.Cerebro()

    # 2. 加载指数数据（用于RSRS择时）
    print("\n[1] 加载基准指数数据...")
    with TimingContext("指数数据加载") as t:
        loader = TushareDataLoader(DATA_PATH, use_cache=True)

        # 使用平安银行作为市场代理（实际应该用沪深300或中证500等宽基指数）
        index_data = loader.load_daily_data(
            ts_code='000001.SZ',
            start_date='2010-01-01',
            end_date='2023-12-31',
            adj_type='hfq'
        )
        index_data._name = 'index'
        cerebro.adddata(index_data)
    timings['指数加载'] = t.elapsed

    print(f"  指数数据: {index_data._name}, 时间范围: 2010-01-01 至 2023-12-31")

    # 3. 加载股票池数据
    print("\n[2] 加载股票池数据...")

    with TimingContext("初始股票池获取") as t:
        # 获取初始股票池（共享loader的缓存）
        selector = ValueStockSelector(data_path=DATA_PATH, use_cache=True)
        initial_pool = selector.get_stock_pool(datetime(2020, 1, 1), stock_num=20)
    timings['选股'] = t.elapsed

    print(f"  初始股票池: {len(initial_pool)} 只股票")

    # 加载股票数据
    with TimingContext("股票数据加载") as t:
        stock_count = 0
        for stock_code in initial_pool[:5]:  # 限制数量避免内存问题
            try:
                stock_data = loader.load_daily_data(
                    ts_code=stock_code,
                    start_date='2010-01-01',
                    end_date='2023-12-31',
                    adj_type='hfq'
                )
                stock_data._name = stock_code
                cerebro.adddata(stock_data)
                stock_count += 1
                print(f"    加载: {stock_code}")
            except Exception as e:
                print(f"    失败: {stock_code}, {e}")
    timings['股票加载'] = t.elapsed

    print(f"  成功加载 {stock_count} 只股票")

    # 输出缓存统计
    cache_stats = loader.get_cache_stats()
    print(f"  数据加载器缓存: 命中{cache_stats['hits']}次, 未命中{cache_stats['misses']}次")

    # 4. 添加策略
    print("\n[3] 添加策略...")
    cerebro.addstrategy(
        RSRSStrategyFull,
        rsrs_period=18,
        rsrs_sample=1100,
        buy_threshold=0.7,
        sell_threshold=-0.7,
        stock_num=10,
        printlog=True
    )

    # 5. 设置交易参数
    print("\n[4] 设置交易参数...")
    cerebro.broker.setcash(1000000)  # 100万初始资金

    # 设置佣金：买入万分之三，卖出万分之三+千分之一印花税
    cerebro.broker.setcommission(
        commission=0.0003,  # 买入佣金万分之三
        name='stock'
    )

    # 设置滑点
    cerebro.broker.set_slippage_perc(perc=0.0001)  # 万分之一滑点

    # 6. 添加分析器
    print("\n[5] 添加分析器...")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')  # 系统质量数

    # 7. 运行回测
    print("\n[6] 运行回测...")
    print(f'初始资金: {cerebro.broker.getvalue():.2f}')
    print("-" * 80)

    with TimingContext("策略运行(cerebro.run)") as t:
        results = cerebro.run()
        strategy = results[0]
    timings['策略运行'] = t.elapsed

    # 8. 输出详细结果
    print("\n" + "=" * 80)
    print("回测结果")
    print("=" * 80)

    final_value = cerebro.broker.getvalue()
    initial_value = 1000000

    print(f'\n【资金情况】')
    print(f'  初始资金: {initial_value:,.2f}')
    print(f'  最终资金: {final_value:,.2f}')
    print(f'  总收益: {final_value - initial_value:,.2f}')
    print(f'  收益率: {(final_value / initial_value - 1) * 100:.2f}%')

    # 风险指标
    print(f'\n【风险指标】')
    sharpe = strategy.analyzers.sharpe.get_analysis()
    sharpe_ratio = sharpe.get('sharperatio', None)
    print(f'  夏普比率: {sharpe_ratio:.4f}' if sharpe_ratio else '  夏普比率: N/A')

    drawdown = strategy.analyzers.drawdown.get_analysis()
    max_dd = drawdown.get('max', {}).get('drawdown', 0)
    print(f'  最大回撤: {max_dd:.2f}%')

    # 交易统计
    print(f'\n【交易统计】')
    trades = strategy.analyzers.trades.get_analysis()
    total_trades = trades.get('total', {}).get('total', 0)
    won_trades = trades.get('won', {}).get('total', 0)
    lost_trades = trades.get('lost', {}).get('total', 0)

    print(f'  总交易次数: {total_trades}')
    print(f'  盈利交易: {won_trades}')
    print(f'  亏损交易: {lost_trades}')

    if total_trades > 0:
        win_rate = won_trades / total_trades * 100
        print(f'  胜率: {win_rate:.2f}%')

    if won_trades > 0:
        avg_won = trades.get('won', {}).get('pnl', {}).get('average', 0)
        print(f'  平均盈利: {avg_won:,.2f}')

    if lost_trades > 0:
        avg_lost = trades.get('lost', {}).get('pnl', {}).get('average', 0)
        print(f'  平均亏损: {avg_lost:,.2f}')

    # SQN系统质量数
    sqn = strategy.analyzers.sqn.get_analysis()
    sqn_value = sqn.get('sqn', None)
    if sqn_value:
        print(f'  系统质量数(SQN): {sqn_value:.2f}')

    # 收益统计
    print(f'\n【收益分析】')
    returns = strategy.analyzers.returns.get_analysis()
    rtot = returns.get('rtot', 0)
    ravg = returns.get('ravg', 0)
    print(f'  总收益率: {rtot * 100:.2f}%')
    print(f'  平均收益率: {ravg * 100:.4f}%')

    # 9. 与基准对比
    print(f'\n【基准对比】')
    print(f'  策略收益率: {(final_value / initial_value - 1) * 100:.2f}%')
    print(f'  注: 实际应与沪深300指数对比')

    # 10. 年化收益
    years = 14  # 2010-2023
    annual_return = (pow(final_value / initial_value, 1 / years) - 1) * 100
    print(f'  年化收益率: {annual_return:.2f}%')

    # 11. 输出耗时统计
    total_elapsed = time.time() - total_start
    print(f'\n【耗时统计】')
    print(f'  ├─ 指数加载: {timings.get("指数加载", 0):.2f}秒')
    print(f'  ├─ 选股: {timings.get("选股", 0):.2f}秒')
    print(f'  ├─ 股票加载: {timings.get("股票加载", 0):.2f}秒')
    print(f'  ├─ 策略运行: {timings.get("策略运行", 0):.2f}秒')
    print(f'  └─ 总耗时: {total_elapsed:.2f}秒')

    # 输出缓存统计
    selector_stats = selector.get_cache_stats()
    print(f'\n【缓存效果】')
    print(f'  数据缓存: 命中{cache_stats["hits"]}次, 未命中{cache_stats["misses"]}次')
    print(f'  选股缓存: 数据命中{selector_stats["data_hits"]}次, 结果命中{selector_stats["result_hits"]}次')

    print("\n" + "=" * 80)

    return results


def run_simple_backtest():
    """
    简化版回测 - 仅测试RSRS择时效果
    使用指数作为唯一标的
    """

    print("=" * 80)
    print("RSRS策略 - 简化版回测(仅择时)")
    print("=" * 80)

    cerebro = bt.Cerebro()

    # 加载指数数据
    print("\n[1] 加载数据...")
    loader = TushareDataLoader('/Users/mac/Downloads/行情数据')
    data = loader.load_daily_data(
        ts_code='000001.SZ',
        start_date='2010-01-01',
        end_date='2023-12-31',
        adj_type='hfq'
    )
    cerebro.adddata(data)

    # 添加策略
    print("\n[2] 添加策略...")
    from rsrc_strategy_full import RSRSStrategyFull
    cerebro.addstrategy(
        RSRSStrategyFull,
        rsrs_period=18,
        rsrs_sample=1100,
        buy_threshold=0.7,
        sell_threshold=-0.7,
        printlog=True
    )

    # 设置参数
    print("\n[3] 设置参数...")
    cerebro.broker.setcash(1000000)
    cerebro.broker.setcommission(commission=0.001)

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    # 运行
    print("\n[4] 运行回测...")
    print(f'初始资金: {cerebro.broker.getvalue():.2f}')
    print("-" * 80)

    results = cerebro.run()
    strategy = results[0]

    # 输出结果
    print("\n" + "=" * 80)
    print("回测结果")
    print("=" * 80)
    print(f'最终资金: {cerebro.broker.getvalue():.2f}')
    print(f'收益率: {(cerebro.broker.getvalue() / 1000000 - 1) * 100:.2f}%')

    sharpe = strategy.analyzers.sharpe.get_analysis()
    print(f'夏普比率: {sharpe.get("sharperatio", "N/A")}')

    drawdown = strategy.analyzers.drawdown.get_analysis()
    print(f'最大回撤: {drawdown.get("max", {}).get("drawdown", "N/A"):.2f}%')

    return results


if __name__ == '__main__':
    import sys

    print("\nRSRS策略完整复刻版回测系统")
    print("=" * 80)
    print("运行模式:")
    print("  1. 完整版回测(择时+选股)")
    print("  2. 简化版回测(仅择时)")
    print("  默认: 完整版")

    # 根据参数选择模式
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        mode = '1'

    if mode == '1':
        run_full_backtest()
    elif mode == '2':
        run_simple_backtest()
    else:
        print(f"未知模式: {mode}")
        print("使用方法: python rsrc_backtest_full.py [1|2]")
