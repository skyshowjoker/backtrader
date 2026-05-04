"""
完整的回测示例 - 使用 Tushare Parquet 数据
演示如何使用本地数据运行回测
"""

from datetime import datetime
import backtrader as bt
from tushare_data_loader import TushareDataLoader


# ==================== 策略定义 ====================

class SmaCrossStrategy(bt.Strategy):
    """双均线交叉策略"""

    params = (
        ('fast_period', 10),
        ('slow_period', 30),
        ('printlog', True),
    )

    def __init__(self):
        # 初始化指标
        self.fast_sma = bt.ind.SMA(period=self.p.fast_period)
        self.slow_sma = bt.ind.SMA(period=self.p.slow_period)
        self.crossover = bt.ind.CrossOver(self.fast_sma, self.slow_sma)

        # 订单变量
        self.order = None

    def next(self):
        # 如果有待处理的订单,不操作
        if self.order:
            return

        # 没有持仓
        if not self.position:
            # 金叉买入
            if self.crossover > 0:
                self.order = self.buy()
                if self.p.printlog:
                    print(f'{self.data.datetime.date(0)}: 买入信号, 价格: {self.data.close[0]:.2f}')
        # 有持仓
        else:
            # 死叉卖出
            if self.crossover < 0:
                self.order = self.sell()
                if self.p.printlog:
                    print(f'{self.data.datetime.date(0)}: 卖出信号, 价格: {self.data.close[0]:.2f}')

    def notify_order(self, order):
        """订单状态通知"""
        if order.status in [order.Completed]:
            if order.isbuy():
                if self.p.printlog:
                    print(f'买入执行: 价格 {order.executed.price:.2f}, '
                          f'成本 {order.executed.value:.2f}, '
                          f'手续费 {order.executed.comm:.2f}')
            else:
                if self.p.printlog:
                    print(f'卖出执行: 价格 {order.executed.price:.2f}, '
                          f'成本 {order.executed.value:.2f}, '
                          f'手续费 {order.executed.comm:.2f}')
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            if self.p.printlog:
                print('订单取消/保证金不足/拒绝')

        self.order = None

    def notify_trade(self, trade):
        """交易通知"""
        if trade.isclosed:
            if self.p.printlog:
                print(f'交易盈亏: 毛利 {trade.pnl:.2f}, 净利 {trade.pnlcomm:.2f}')


# ==================== 回测主程序 ====================

def run_backtest():
    """运行回测"""

    print("=" * 80)
    print("Backtrader 回测系统 - 使用本地 Tushare 数据")
    print("=" * 80)

    # 1. 创建 Cerebro 引擎
    cerebro = bt.Cerebro()

    # 2. 加载数据
    print("\n[1] 加载数据...")
    loader = TushareDataLoader('/Users/mac/Downloads/行情数据')

    # 加载日线数据
    data = loader.load_daily_data(
        ts_code='000001.SZ',  # 平安银行
        start_date='2020-01-01',
        end_date='2023-12-31',
        adj_type='hfq'  # 后复权
    )

    # 添加数据到引擎
    cerebro.adddata(data)

    # 3. 添加策略
    print("\n[2] 添加策略...")
    cerebro.addstrategy(SmaCrossStrategy,
                       fast_period=10,
                       slow_period=30,
                       printlog=True)

    # 4. 设置初始资金和佣金
    print("\n[3] 设置回测参数...")
    cerebro.broker.setcash(100000.0)  # 10万初始资金
    cerebro.broker.setcommission(commission=0.001)  # 0.1% 佣金

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
    print(f'总收益: {cerebro.broker.getvalue() - 100000:.2f}')
    print(f'收益率: {(cerebro.broker.getvalue() / 100000 - 1) * 100:.2f}%')

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
        print("提示: 需要安装 matplotlib: pip install matplotlib")

    return results


def run_multi_stock_backtest():
    """多股票回测示例"""

    print("=" * 80)
    print("多股票回测示例")
    print("=" * 80)

    cerebro = bt.Cerebro()

    # 加载多只股票
    loader = TushareDataLoader()
    stocks = ['000001.SZ', '000002.SZ', '600000.SH']

    for stock in stocks:
        try:
            data = loader.load_daily_data(
                ts_code=stock,
                start_date='2022-01-01',
                end_date='2023-12-31',
                adj_type='hfq'
            )
            cerebro.adddata(data)
            print(f"成功加载: {stock}")
        except Exception as e:
            print(f"加载失败 {stock}: {e}")

    # 添加策略
    cerebro.addstrategy(SmaCrossStrategy, printlog=False)

    # 设置参数
    cerebro.broker.setcash(300000.0)
    cerebro.broker.setcommission(commission=0.001)

    # 运行
    print(f'\n初始资金: {cerebro.broker.getvalue():.2f}')
    results = cerebro.run()
    print(f'最终资金: {cerebro.broker.getvalue():.2f}')
    print(f'收益率: {(cerebro.broker.getvalue() / 300000 - 1) * 100:.2f}%')


def run_minute_backtest():
    """分钟线回测示例"""

    print("=" * 80)
    print("分钟线回测示例 (15分钟)")
    print("=" * 80)

    cerebro = bt.Cerebro()

    # 加载分钟数据
    loader = TushareDataLoader()
    data = loader.load_minute_data(
        ts_code='000001.SZ',
        freq='15min',
        start_date='2023-06-01',
        end_date='2023-06-30',
        adj_type='qfq'
    )

    cerebro.adddata(data)

    # 添加策略
    cerebro.addstrategy(SmaCrossStrategy,
                       fast_period=20,
                       slow_period=60,
                       printlog=True)

    # 设置参数
    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.001)

    # 运行
    print(f'\n初始资金: {cerebro.broker.getvalue():.2f}')
    results = cerebro.run()
    print(f'最终资金: {cerebro.broker.getvalue():.2f}')
    print(f'收益率: {(cerebro.broker.getvalue() / 100000 - 1) * 100:.2f}%')


if __name__ == '__main__':
    # 运行日线回测
    run_backtest()

    # 运行多股票回测
    # run_multi_stock_backtest()

    # 运行分钟线回测
    # run_minute_backtest()
