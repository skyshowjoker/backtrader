"""
RSRS策略快速测试版
使用较短的时间范围快速验证策略效果
"""

from datetime import datetime
import backtrader as bt
from tushare_data_loader import TushareDataLoader
from rsrc_strategy import RSRSStrategy


def quick_test():
    """快速测试RSRS策略"""

    print("=" * 80)
    print("RSRS策略快速测试 (2020-2023)")
    print("=" * 80)

    # 创建引擎
    cerebro = bt.Cerebro()

    # 加载数据(只测试4年)
    print("\n[1] 加载数据...")
    loader = TushareDataLoader('/Users/mac/Downloads/行情数据')
    data = loader.load_daily_data(
        ts_code='000001.SZ',
        start_date='2020-01-01',
        end_date='2023-12-31',
        adj_type='hfq'
    )
    cerebro.adddata(data)

    # 添加策略
    print("\n[2] 添加策略...")
    cerebro.addstrategy(
        RSRSStrategy,
        rsrs_period=18,
        rsrs_sample=500,  # 减少样本数
        buy_threshold=0.7,
        sell_threshold=-0.7,
        printlog=True
    )

    # 设置参数
    print("\n[3] 设置参数...")
    cerebro.broker.setcash(100000)
    cerebro.broker.setcommission(commission=0.001)

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    # 运行回测
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
    print(f'总收益: {cerebro.broker.getvalue() - 100000:.2f}')
    print(f'收益率: {(cerebro.broker.getvalue() / 100000 - 1) * 100:.2f}%')

    # 风险指标
    sharpe = strategy.analyzers.sharpe.get_analysis()
    print(f'\n夏普比率: {sharpe.get("sharperatio", "N/A")}')

    drawdown = strategy.analyzers.drawdown.get_analysis()
    print(f'最大回撤: {drawdown.get("max", {}).get("drawdown", "N/A"):.2f}%')

    # 交易统计
    trades = strategy.analyzers.trades.get_analysis()
    print(f'\n总交易次数: {trades.get("total", {}).get("total", 0)}')
    print(f'盈利交易: {trades.get("won", {}).get("total", 0)}')
    print(f'亏损交易: {trades.get("lost", {}).get("total", 0)}')

    return results


if __name__ == '__main__':
    quick_test()
