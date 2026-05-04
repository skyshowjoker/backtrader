"""
RSRS价值选股策略 - Backtrader实现版
基于聚宽策略: https://www.joinquant.com/post/15002

策略思路:
1. 选股: 基于PB和ROE的价值选股
2. 择时: RSRS(阻力支撑相对强度)指标择时
3. 持仓: 满足条件时持有10只股票,不满足时空仓
"""

import backtrader as bt
import pandas as pd
import numpy as np
import statsmodels.api as sm
from tushare_data_loader import TushareDataLoader


class RSRSIndicator(bt.Indicator):
    """RSRS指标 - 阻力支撑相对强度"""

    lines = ('zscore', 'zscore_rightdev',)

    params = (
        ('period', 18),      # 统计周期N
        ('sample', 1100),    # 统计样本长度M
    )

    def __init__(self):
        self.beta_history = []
        self.r2_history = []

        # 需要足够的数据才能计算
        self.addminperiod(self.p.period)

    def next(self):
        # 获取过去N天的高低价格
        highs = np.array([self.data.high[-i] for i in range(self.p.period)])
        lows = np.array([self.data.low[-i] for i in range(self.p.period)])

        # OLS回归: high = alpha + beta * low
        X = sm.add_constant(lows)
        model = sm.OLS(highs, X)
        results = model.fit()

        beta = results.params[1]  # 斜率
        r2 = results.rsquared      # R²决定系数

        # 保存历史数据
        self.beta_history.append(beta)
        self.r2_history.append(r2)

        # 确保有足够的历史数据
        if len(self.beta_history) < self.p.sample:
            self.lines.zscore[0] = 0
            self.lines.zscore_rightdev[0] = 0
            return

        # 取最近M个beta值
        section = self.beta_history[-self.p.sample:]

        # 计算标准化的RSRS指标
        mu = np.mean(section)
        sigma = np.std(section)

        if sigma == 0:
            zscore = 0
        else:
            zscore = (section[-1] - mu) / sigma

        # 计算右偏RSRS标准分 = zscore * beta * r2
        zscore_rightdev = zscore * beta * r2

        # 赋值给输出线
        self.lines.zscore[0] = zscore
        self.lines.zscore_rightdev[0] = zscore_rightdev


class ValueSelection:
    """价值选股工具类"""

    def __init__(self, data_loader, data_path='/Users/mac/Downloads/行情数据'):
        self.data_loader = data_loader
        self.data_path = data_path
        self.basic_file = data_path + '/stock_basic_data.parquet'

    def get_stock_pool(self, date, stock_num=10):
        """
        获取指定日期的股票池
        选股逻辑:
        1. PB > 0 且 ROE > 0
        2. 按PB升序排列
        3. 对PB和1/ROE进行排名打分
        4. 选择综合得分最低的stock_num只股票
        """
        try:
            # 读取基础数据
            df = pd.read_parquet(self.basic_file)

            # 筛选条件
            df = df[(df['pb'] > 0) & (df['roe'] > 0)]

            if len(df) == 0:
                return []

            # 计算得分
            df['pb_rank'] = df['pb'].rank()
            df['roe_rank'] = (1 / df['roe']).rank()
            df['score'] = df['pb_rank'] + df['roe_rank']

            # 按得分排序,取前stock_num只
            df = df.nsmallest(stock_num, 'score')

            return df['ts_code'].tolist()

        except Exception as e:
            print(f"选股失败: {e}")
            return []


class RSRSStrategy(bt.Strategy):
    """RSRS价值选股策略"""

    params = (
        ('rsrs_period', 18),        # RSRS周期
        ('rsrs_sample', 1100),      # RSRS样本数
        ('buy_threshold', 0.7),     # 买入阈值
        ('sell_threshold', -0.7),   # 卖出阈值
        ('stock_num', 10),          # 持仓股票数
        ('index_code', '000300.SH'), # 基准指数(沪深300)
        ('data_loader', None),      # 数据加载器
        ('printlog', True),
    )

    def __init__(self):
        # RSRS指标(用于择时)
        self.rsrs = RSRSIndicator(
            self.data0,
            period=self.p.rsrs_period,
            sample=self.p.rsrs_sample
        )

        # 订单字典
        self.orders = {}

        # 选股工具
        if self.p.data_loader:
            self.selector = ValueSelection(self.p.data_loader)
        else:
            self.selector = None

        # 记录交易天数
        self.days = 0

        # 缓存股票池
        self.stock_pool = []

    def next(self):
        self.days += 1

        # 获取RSRS指标值
        zscore_rightdev = self.rsrs.zscore_rightdev[0]

        if self.p.printlog and self.days % 20 == 0:
            print(f'{self.data0.datetime.date(0)}: RSRS指标 = {zscore_rightdev:.4f}')

        # 择时信号判断
        if zscore_rightdev > self.p.buy_threshold:
            # 市场风险合理,执行选股买入
            if self.p.printlog:
                print(f'{self.data0.datetime.date(0)}: 市场风险合理,RSRS={zscore_rightdev:.4f}')

            # 选股
            if self.selector:
                current_date = self.data0.datetime.date(0)
                self.stock_pool = self.selector.get_stock_pool(
                    current_date,
                    self.p.stock_num
                )

                if self.p.printlog and self.stock_pool:
                    print(f'选中股票: {self.stock_pool[:5]}...')

            # 这里简化为买入指数(实际应该买入选出的股票)
            if not self.getposition(self.data0):
                self.orders[self.data0._name] = self.buy()

        elif zscore_rightdev < self.p.sell_threshold:
            # 市场风险过大,清仓
            if self.p.printlog:
                print(f'{self.data0.datetime.date(0)}: 市场风险过大,清仓,RSRS={zscore_rightdev:.4f}')

            if self.getposition(self.data0):
                self.orders[self.data0._name] = self.sell()

    def notify_order(self, order):
        """订单状态通知"""
        if order.status in [order.Completed]:
            if order.isbuy():
                if self.p.printlog:
                    print(f'买入执行: {order.data._name}, '
                          f'价格 {order.executed.price:.2f}, '
                          f'数量 {order.executed.size:.2f}')
            else:
                if self.p.printlog:
                    print(f'卖出执行: {order.data._name}, '
                          f'价格 {order.executed.price:.2f}, '
                          f'数量 {order.executed.size:.2f}')
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            if self.p.printlog:
                print(f'订单失败: {order.data._name}')

        # 清除订单记录
        if order.data._name in self.orders:
            del self.orders[order.data._name]

    def notify_trade(self, trade):
        """交易通知"""
        if trade.isclosed:
            if self.p.printlog:
                print(f'交易完成: 毛利 {trade.pnl:.2f}, 净利 {trade.pnlcomm:.2f}')


class RSRSStrategyMultiStock(bt.Strategy):
    """RSRS策略 - 多股票版本"""

    params = (
        ('rsrs_period', 18),
        ('rsrs_sample', 1100),
        ('buy_threshold', 0.7),
        ('sell_threshold', -0.7),
        ('stock_num', 10),
        ('printlog', True),
    )

    def __init__(self):
        # 对第一个数据(指数)应用RSRS指标
        self.rsrs = RSRSIndicator(
            self.data0,
            period=self.p.rsrs_period,
            sample=self.p.rsrs_sample
        )

        self.orders = {}
        self.days = 0

    def next(self):
        self.days += 1

        # RSRS择时信号
        zscore_rightdev = self.rsrs.zscore_rightdev[0]

        if self.p.printlog and self.days % 50 == 0:
            print(f'{self.data0.datetime.date(0)}: RSRS={zscore_rightdev:.4f}')

        # 买入信号
        if zscore_rightdev > self.p.buy_threshold:
            # 平均分配资金到所有股票(除了第一个指数数据)
            stocks = self.datas[1:]  # 排除第一个指数
            if len(stocks) > 0:
                weight = 0.95 / len(stocks)  # 留5%现金

                for stock in stocks:
                    if not self.getposition(stock):
                        size = (self.broker.getcash() * weight) / stock.close[0]
                        if size > 0:
                            self.orders[stock._name] = self.buy(data=stock, size=size)

        # 卖出信号
        elif zscore_rightdev < self.p.sell_threshold:
            for stock in self.datas[1:]:
                if self.getposition(stock):
                    self.orders[stock._name] = self.sell(data=stock)

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                if self.p.printlog:
                    print(f'买入: {order.data._name} @ {order.executed.price:.2f}')
            else:
                if self.p.printlog:
                    print(f'卖出: {order.data._name} @ {order.executed.price:.2f}')
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(f'订单失败: {order.data._name}')

        if order.data._name in self.orders:
            del self.orders[order.data._name]

    def notify_trade(self, trade):
        if trade.isclosed and self.p.printlog:
            print(f'交易盈亏: {trade.pnl:.2f}')


if __name__ == '__main__':
    print("RSRS策略模块加载成功")
    print("请运行 rsrc_backtest.py 进行回测")
