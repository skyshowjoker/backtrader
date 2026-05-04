"""
快速开始示例 - 最简单的回测
演示如何用最少的代码运行回测
"""

import backtrader as bt
from tushare_data_loader import TushareDataLoader


# 1. 定义简单策略
class SimpleStrategy(bt.Strategy):
    """简单的均线策略"""

    def __init__(self):
        self.sma = bt.ind.SMA(period=20)  # 20日均线

    def next(self):
        if not self.position:  # 没有持仓
            if self.data.close[0] > self.sma[0]:  # 价格上穿均线
                self.buy()
        else:  # 有持仓
            if self.data.close[0] < self.sma[0]:  # 价格下穿均线
                self.sell()


# 2. 创建回测引擎
cerebro = bt.Cerebro()

# 3. 加载数据
loader = TushareDataLoader('/Users/mac/Downloads/行情数据')
data = loader.load_daily_data(
    ts_code='000001.SZ',      # 股票代码
    start_date='2023-01-01',  # 开始日期
    end_date='2023-12-31',    # 结束日期
    adj_type='hfq'           # 后复权
)
cerebro.adddata(data)

# 4. 添加策略
cerebro.addstrategy(SimpleStrategy)

# 5. 设置资金
cerebro.broker.setcash(100000)

# 6. 运行回测
print(f'初始资金: {cerebro.broker.getvalue():.2f}')
results = cerebro.run()
print(f'最终资金: {cerebro.broker.getvalue():.2f}')
print(f'收益率: {(cerebro.broker.getvalue() / 100000 - 1) * 100:.2f}%')
