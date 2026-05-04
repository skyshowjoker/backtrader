"""
RSRS价值选股策略 - 回测脚本
完整实现聚宽策略的Backtrader版本
"""

from datetime import datetime
import backtrader as bt
import pandas as pd
import numpy as np
from tushare_data_loader import TushareDataLoader
from rsrc_strategy import RSRSStrategy, RSRSStrategyMultiStock


def run_rsrc_backtest_simple():
    """
    简化版RSRS回测 - 使用指数作为标的
    用于测试RSRS择时指标的效果
    """

    print("=" * 80)
    print("RSRS策略回测 - 简化版(指数择时)")
    print("=" * 80)

    # 1. 创建引擎
    cerebro = bt.Cerebro()

    # 2. 加载指数数据(使用沪深300替代,这里用平安银行作为示例)
    print("\n[1] 加载指数数据...")
    loader = TushareDataLoader('/Users/mac/Downloads/行情数据')

    # 由于没有沪深300数据,用平安银行作为市场代理
    data = loader.load_daily_data(
        ts_code='000001.SZ',
        start_date='2010-01-01',
        end_date='2023-12-31',
        adj_type='hfq'
    )
    cerebro.adddata(data)

    # 3. 添加策略
    print("\n[2] 添加RSRS策略...")
    cerebro.addstrategy(
        RSRSStrategy,
        rsrs_period=18,
        rsrs_sample=1100,
        buy_threshold=0.7,
        sell_threshold=-0.7,
        stock_num=10,
        printlog=True
    )

    # 4. 设置参数
    print("\n[3] 设置回测参数...")
    cerebro.broker.setcash(1000000)  # 100万初始资金
    cerebro.broker.setcommission(commission=0.001)  # 0.1%佣金

    # 5. 添加分析器
    print("\n[4] 添加分析器...")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    # 6. 运行回测
    print("\n[5] 运行回测...")
    print(f'初始资金: {cerebro.broker.getvalue():.2f}')
    print("-" * 80)

    results = cerebro.run()
    strategy = results[0]

    # 7. 输出结果
    print("\n" + "=" * 80)
    print("回测结果")
    print("=" * 80)
    print(f'最终资金: {cerebro.broker.getvalue():.2f}')
    print(f'总收益: {cerebro.broker.getvalue() - 1000000:.2f}')
    print(f'收益率: {(cerebro.broker.getvalue() / 1000000 - 1) * 100:.2f}%')

    # 分析器结果
    print("\n--- 风险指标 ---")
    sharpe = strategy.analyzers.sharpe.get_analysis()
    print(f'夏普比率: {sharpe.get("sharperatio", "N/A")}')

    drawdown = strategy.analyzers.drawdown.get_analysis()
    print(f'最大回撤: {drawdown.get("max", {}).get("drawdown", "N/A"):.2f}%')

    # 交易统计
    trades = strategy.analyzers.trades.get_analysis()
    print("\n--- 交易统计 ---")
    print(f'总交易次数: {trades.get("total", {}).get("total", 0)}')
    print(f'盈利交易: {trades.get("won", {}).get("total", 0)}')
    print(f'亏损交易: {trades.get("lost", {}).get("total", 0)}')

    if trades.get("won", {}).get("total", 0) > 0:
        print(f'平均盈利: {trades.get("won", {}).get("pnl", {}).get("average", 0):.2f}')
    if trades.get("lost", {}).get("total", 0) > 0:
        print(f'平均亏损: {trades.get("lost", {}).get("pnl", {}).get("average", 0):.2f}')

    # 8. 绘图
    print("\n[6] 绘制图表...")
    try:
        cerebro.plot(style='candlestick', barup='red', bardown='green')
    except Exception as e:
        print(f"绘图失败: {e}")

    return results


def run_rsrc_backtest_multistock():
    """
    多股票版RSRS回测 - 完整策略
    RSRS择时 + 多股票持仓
    """

    print("=" * 80)
    print("RSRS策略回测 - 多股票版")
    print("=" * 80)

    # 1. 创建引擎
    cerebro = bt.Cerebro()

    # 2. 加载数据
    print("\n[1] 加载指数和股票数据...")
    loader = TushareDataLoader('/Users/mac/Downloads/行情数据')

    # 加载指数数据(市场代理)
    index_data = loader.load_daily_data(
        ts_code='000001.SZ',
        start_date='2020-01-01',
        end_date='2023-12-31',
        adj_type='hfq'
    )
    cerebro.adddata(index_data)

    # 加载多只股票(模拟选股结果)
    stocks = ['000002.SZ', '600000.SH', '000006.SZ', '000009.SZ']
    for stock in stocks:
        try:
            stock_data = loader.load_daily_data(
                ts_code=stock,
                start_date='2020-01-01',
                end_date='2023-12-31',
                adj_type='hfq'
            )
            cerebro.adddata(stock_data)
            print(f"  加载股票: {stock}")
        except Exception as e:
            print(f"  加载失败 {stock}: {e}")

    # 3. 添加策略
    print("\n[2] 添加RSRS多股票策略...")
    cerebro.addstrategy(
        RSRSStrategyMultiStock,
        rsrs_period=18,
        rsrs_sample=500,  # 减少样本数以适应较短的历史数据
        buy_threshold=0.7,
        sell_threshold=-0.7,
        printlog=True
    )

    # 4. 设置参数
    print("\n[3] 设置回测参数...")
    cerebro.broker.setcash(1000000)
    cerebro.broker.setcommission(commission=0.001)

    # 5. 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')

    # 6. 运行回测
    print("\n[4] 运行回测...")
    print(f'初始资金: {cerebro.broker.getvalue():.2f}')
    print("-" * 80)

    results = cerebro.run()
    strategy = results[0]

    # 7. 输出结果
    print("\n" + "=" * 80)
    print("回测结果")
    print("=" * 80)
    print(f'最终资金: {cerebro.broker.getvalue():.2f}')
    print(f'收益率: {(cerebro.broker.getvalue() / 1000000 - 1) * 100:.2f}%')

    # 分析器结果
    sharpe = strategy.analyzers.sharpe.get_analysis()
    print(f'夏普比率: {sharpe.get("sharperatio", "N/A")}')

    drawdown = strategy.analyzers.drawdown.get_analysis()
    print(f'最大回撤: {drawdown.get("max", {}).get("drawdown", "N/A"):.2f}%')

    return results


def test_rsrs_indicator():
    """
    测试RSRS指标计算
    """

    print("=" * 80)
    print("RSRS指标测试")
    print("=" * 80)

    import matplotlib.pyplot as plt

    # 加载数据
    loader = TushareDataLoader()
    data = loader.load_daily_data('000001.SZ', '2010-01-01', '2023-12-31')

    # 创建引擎
    cerebro = bt.Cerebro()
    cerebro.adddata(data)

    # 添加策略(仅用于计算指标)
    class TestStrategy(bt.Strategy):
        def __init__(self):
            from rsrc_strategy import RSRSIndicator
            self.rsrs = RSRSIndicator(self.data, period=18, sample=1100)
            self.values = []

        def next(self):
            if len(self.rsrs.zscore_rightdev) > 0:
                zscore = self.rsrs.zscore_rightdev[0]
                self.values.append({
                    'date': self.data.datetime.date(0),
                    'zscore': zscore,
                    'close': self.data.close[0]
                })

    cerebro.addstrategy(TestStrategy)
    results = cerebro.run()

    # 提取数据
    strategy = results[0]
    df = pd.DataFrame(strategy.values)

    print(f"\n计算完成,共 {len(df)} 个数据点")
    print(f"RSRS指标范围: {df['zscore'].min():.4f} 至 {df['zscore'].max():.4f}")

    # 绘制RSRS指标
    plt.figure(figsize=(12, 6))

    plt.subplot(2, 1, 1)
    plt.plot(df['date'], df['close'], label='Close Price')
    plt.title('Stock Price')
    plt.legend()

    plt.subplot(2, 1, 2)
    plt.plot(df['date'], df['zscore'], label='RSRS Z-Score', color='orange')
    plt.axhline(y=0.7, color='r', linestyle='--', label='Buy Threshold')
    plt.axhline(y=-0.7, color='g', linestyle='--', label='Sell Threshold')
    plt.title('RSRS Indicator')
    plt.legend()

    plt.tight_layout()
    plt.savefig('/Users/mac/PycharmProjects/backtrader/output/rsrs_indicator.png')
    print("\n图表已保存到: output/rsrs_indicator.png")

    return df


if __name__ == '__main__':
    import sys

    # 创建输出目录
    import os
    os.makedirs('output', exist_ok=True)

    print("\nRSRS策略回测系统")
    print("=" * 80)
    print("选择运行模式:")
    print("  1. 简化版回测(指数择时)")
    print("  2. 多股票版回测")
    print("  3. 测试RSRS指标")
    print("  默认: 运行简化版")

    # 根据参数选择模式
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        mode = '1'

    if mode == '1':
        run_rsrc_backtest_simple()
    elif mode == '2':
        run_rsrc_backtest_multistock()
    elif mode == '3':
        test_rsrs_indicator()
    else:
        print(f"未知模式: {mode}")
        print("使用方法: python rsrc_backtest.py [1|2|3]")