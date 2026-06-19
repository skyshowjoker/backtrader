"""SMA 双均线交叉策略 - 内置示例策略

经典的双均线交叉策略，适合单股回测演示：
- 短期均线上穿长期均线 → 买入
- 短期均线下穿长期均线 → 卖出
"""

import backtrader as bt


class SMACrossStrategy(bt.Strategy):
    """SMA 双均线交叉策略

    参数:
        period1: 短期均线周期（默认10）
        period2: 长期均线周期（默认30）
        printlog: 是否打印日志
    """

    params = (
        ('period1', 10),
        ('period2', 30),
        ('printlog', False),
    )

    def __init__(self):
        self.sma1 = bt.ind.SMA(period=self.p.period1)
        self.sma2 = bt.ind.SMA(period=self.p.period2)
        self.crossover = bt.ind.CrossOver(self.sma1, self.sma2)
        self.order = None

    def log(self, txt, dt=None):
        if self.p.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'[{dt}] {txt}')

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'买入执行: 价格={order.executed.price:.2f}, '
                         f'数量={order.executed.size:.0f}, '
                         f'成本={order.executed.value:.2f}')
            else:
                self.log(f'卖出执行: 价格={order.executed.price:.2f}, '
                         f'数量={order.executed.size:.0f}')

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('订单取消/保证金不足/拒绝')

        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.log(f'交易盈亏: 毛利={trade.pnl:.2f}, 净利={trade.pnlcomm:.2f}')

    def next(self):
        if self.order:
            return

        if not self.position:
            if self.crossover[0] > 0:  # 金叉
                self.order = self.buy()
                self.log(f'买入信号 (SMA{self.p.period1}上穿SMA{self.p.period2})')
        else:
            if self.crossover[0] < 0:  # 死叉
                self.order = self.sell()
                self.log(f'卖出信号 (SMA{self.p.period1}下穿SMA{self.p.period2})')
