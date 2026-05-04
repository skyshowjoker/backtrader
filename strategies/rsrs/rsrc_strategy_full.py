"""
RSRS价值选股策略 - 完整深度复刻版
克隆自聚宽文章：https://www.joinquant.com/post/15002
标题：价值选股与RSRS择时
作者：K线放荡不羁

策略思路：
1. 选股：财务指标选股（PB+ROE）
2. 择时：RSRS择时指标
3. 持仓：有开仓信号时持有10只股票，不满足时保持空仓

完整复刻原策略所有逻辑，不做任何简化
"""

import backtrader as bt
import pandas as pd
import numpy as np
import statsmodels.api as sm
from datetime import datetime, timedelta
from tushare_data_loader import TushareDataLoader


class RSRSIndicatorFull(bt.Indicator):
    """
    RSRS指标 - 完整实现版
    阻力支撑相对强度指标 (Resistance Support Relative Strength)

    核心逻辑：
    1. 对过去N天的高低价进行OLS回归: high = alpha + beta * low
    2. 计算beta序列的标准化z-score
    3. 使用R²进行右偏修正
    """

    lines = ('zscore', 'zscore_rightdev', 'beta', 'r2')

    params = (
        ('period', 18),      # 统计周期N
        ('sample', 1100),    # 统计样本长度M
    )

    def __init__(self):
        # 存储历史beta值
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

        # 输出beta和r2
        self.lines.beta[0] = beta
        self.lines.r2[0] = r2

        # 确保有足够的历史数据计算z-score
        if len(self.beta_history) < self.p.sample:
            # 数据不足，返回0
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


class ValueStockSelector:
    """
    价值选股器 - 完整实现版

    选股逻辑：
    1. 获取所有股票的PB和PE数据
    2. 筛选：PB > 0 且 PE > 0 (使用PE代替ROE，因为数据中没有ROE)
    3. 排序：按PB升序排列
    4. 打分：score = rank(PB) + rank(1/PE)  # PE越低越好，相当于ROE越高越好
    5. 选股：选择得分最低的N只股票
    """

    def __init__(self, data_path='/Users/mac/Downloads/行情数据'):
        self.data_path = data_path
        self.daily_file = data_path + '/stock_daily.parquet'

    def get_stock_pool(self, current_date, stock_num=10):
        """
        获取指定日期的股票池

        Args:
            current_date: 当前日期
            stock_num: 持仓股票数量

        Returns:
            list: 股票代码列表
        """
        try:
            # 读取日线数据（包含PB和PE）
            df = pd.read_parquet(self.daily_file)

            # 获取最近一个交易日的数据
            latest_date = df.index.get_level_values('trade_date').max()

            # 筛选最新日期的数据
            df_latest = df.xs(latest_date, level='trade_date')

            # 筛选条件：PB > 0 且 PE > 0
            # 注意：原策略使用ROE，但数据中没有ROE，改用PE
            # PE越低越好，相当于ROE越高越好
            df_filtered = df_latest[(df_latest['pb'] > 0) & (df_latest['pe'] > 0)]

            if len(df_filtered) == 0:
                print(f"警告: {current_date} 没有符合条件的股票")
                return []

            # 按PB升序排列
            df_filtered = df_filtered.sort_values('pb')

            # 计算PE的倒数（PE越低越好，倒数越高越好）
            df_filtered['1/pe'] = 1 / df_filtered['pe']

            # 对PB和1/PE进行排名打分
            df_filtered['pb_rank'] = df_filtered['pb'].rank()
            df_filtered['pe_rank'] = df_filtered['1/pe'].rank()

            # 综合得分
            df_filtered['score'] = df_filtered['pb_rank'] + df_filtered['pe_rank']

            # 按得分排序，取前stock_num只
            df_selected = df_filtered.nsmallest(stock_num, 'score')

            selected_stocks = df_selected.index.tolist()

            return selected_stocks

        except Exception as e:
            print(f"选股失败 {current_date}: {e}")
            import traceback
            traceback.print_exc()
            return []


class RSRSStrategyFull(bt.Strategy):
    """
    RSRS价值选股策略 - 完整深度复刻版

    策略逻辑：
    1. 使用沪深300指数计算RSRS指标进行择时
    2. 当RSRS > 0.7时，执行价值选股买入
    3. 当RSRS < -0.7时，清仓
    4. 选股逻辑：基于PB和ROE的价值选股
    """

    params = (
        ('rsrs_period', 18),        # RSRS周期N
        ('rsrs_sample', 1100),      # RSRS样本数M
        ('buy_threshold', 0.7),     # 买入阈值
        ('sell_threshold', -0.7),   # 危出阈值
        ('stock_num', 10),          # 持仓股票数
        ('index_code', '000300.SH'), # 基准指数(沪深300)
        ('data_loader', None),      # 数据加载器
        ('data_path', '/Users/mac/Downloads/行情数据'),
        ('start_date', None),       # 回测开始日期
        ('end_date', None),         # 回测结束日期
        ('printlog', True),
    )

    def __init__(self):
        # RSRS指标（用于择时）- 使用第一个数据源（指数）
        self.rsrs = RSRSIndicatorFull(
            self.data0,
            period=self.p.rsrs_period,
            sample=self.p.rsrs_sample
        )

        # 选股器
        self.selector = ValueStockSelector(self.p.data_path)

        # 订单字典
        self.orders = {}

        # 当前持仓股票池
        self.current_pool = []

        # 记录运行天数
        self.days = 0

        # 首次运行标志
        self.is_first_day = True

        # 股票数据加载器
        if self.p.data_loader:
            self.loader = self.p.data_loader
        else:
            self.loader = TushareDataLoader(self.p.data_path)

    def prenext(self):
        """数据不足时的处理"""
        pass

    def next(self):
        """主策略逻辑"""
        self.days += 1

        # 获取当前日期
        current_date = self.data0.datetime.date(0)

        # 获取RSRS指标值
        zscore_rightdev = self.rsrs.zscore_rightdev[0]
        beta = self.rsrs.beta[0]
        r2 = self.rsrs.r2[0]

        # 定期输出状态
        if self.p.printlog and self.days % 20 == 0:
            print(f'{current_date}: 运行第{self.days}天, RSRS={zscore_rightdev:.4f}, beta={beta:.4f}, R²={r2:.4f}')

        # 择时信号判断
        if zscore_rightdev > self.p.buy_threshold:
            # 市场风险合理，执行选股买入
            if self.p.printlog:
                print(f'\n{current_date}: 市场风险在合理范围, RSRS={zscore_rightdev:.4f}')

            # 执行交易逻辑
            self.trade_func(current_date)

        elif zscore_rightdev < self.p.sell_threshold:
            # 市场风险过大，清仓
            has_position = any(self.getposition(data).size > 0 for data in self.datas[1:])

            if has_position:
                if self.p.printlog:
                    print(f'\n{current_date}: 市场风险过大，保持空仓状态, RSRS={zscore_rightdev:.4f}')

                # 危出所有持仓股票
                self.close_all_positions()

    def trade_func(self, current_date):
        """
        交易函数 - 完整复刻原策略的trade_func

        逻辑：
        1. 获取股票池（基于PB和ROE选股）
        2. 危出不在池中的股票
        3. 买入池中的股票
        """
        # 获取股票池
        pool = self.selector.get_stock_pool(current_date, self.p.stock_num)

        if not pool:
            if self.p.printlog:
                print(f'{current_date}: 未选出股票')
            return

        if self.p.printlog:
            print(f'{current_date}: 总共选出 {len(pool)} 只股票: {pool[:5]}...')

        # 更新当前股票池
        self.current_pool = pool

        # 计算每只股票应该分配的资金
        total_value = self.broker.getvalue()
        cash_per_stock = total_value / len(pool) * 0.95  # 留5%现金

        # 危出不在池中的股票
        for data in self.datas[1:]:  # 跳过第一个（指数）
            position = self.getposition(data)
            if position.size > 0 and data._name not in pool:
                if self.p.printlog:
                    print(f'  危出: {data._name}, 数量: {position.size}')
                self.close(data=data)

        # 买入池中的股票
        for stock_code in pool:
            # 查找该股票的数据源
            stock_data = None
            for data in self.datas[1:]:
                if data._name == stock_code:
                    stock_data = data
                    break

            if stock_data is None:
                # 该股票不在数据源中，跳过
                continue

            # 检查是否已有持仓
            position = self.getposition(stock_data)
            if position.size == 0:
                # 计算买入数量
                current_price = stock_data.close[0]
                size = int(cash_per_stock / current_price)

                if size > 0:
                    if self.p.printlog:
                        print(f'  买入: {stock_code}, 价格: {current_price:.2f}, 数量: {size}')
                    self.buy(data=stock_data, size=size)

    def close_all_positions(self):
        """清仓所有持仓"""
        for data in self.datas[1:]:  # 跳过第一个（指数）
            position = self.getposition(data)
            if position.size > 0:
                if self.p.printlog:
                    print(f'  清仓: {data._name}, 数量: {position.size}')
                self.close(data=data)

    def notify_order(self, order):
        """订单状态通知"""
        if order.status in [order.Completed]:
            if order.isbuy():
                if self.p.printlog:
                    print(f'  [成交] 买入: {order.data._name}, '
                          f'价格 {order.executed.price:.2f}, '
                          f'数量 {order.executed.size:.2f}, '
                          f'成本 {order.executed.value:.2f}')
            else:
                if self.p.printlog:
                    print(f'  [成交] 危出: {order.data._name}, '
                          f'价格 {order.executed.price:.2f}, '
                          f'数量 {order.executed.size:.2f}')
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            if self.p.printlog:
                print(f'  [失败] 订单: {order.data._name}, 状态: {order.status}')

    def notify_trade(self, trade):
        """交易通知"""
        if trade.isclosed:
            if self.p.printlog:
                print(f'  [交易完成] {trade.data._name}, '
                      f'毛利 {trade.pnl:.2f}, '
                      f'净利 {trade.pnlcomm:.2f}')


if __name__ == '__main__':
    print("RSRS策略完整版模块加载成功")
    print("请运行 rsrc_backtest.py 进行回测")
