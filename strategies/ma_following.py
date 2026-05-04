#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
"""
均线跟随策略 (Moving Average Following Strategy)

策略逻辑：
1. 价格上穿均线时买入
2. 价格下穿均线时卖出
3. 使用百分比仓位管理
4. 包含止损和止盈机制
"""

from datetime import datetime
import backtrader as bt


class MovingAverageFollowing(bt.Strategy):
    """均线跟随策略"""

    # 策略参数
    params = (
        ('ma_period', 20),           # 均线周期
        ('ma_type', 'SMA'),          # 均线类型：SMA, EMA
        ('stop_loss', 0.05),         # 止损比例 5%
        ('take_profit', 0.10),       # 止盈比例 10%
        ('position_pct', 0.95),      # 仓位比例 95%
        ('printlog', False),         # 是否打印日志
    )

    def __init__(self):
        """初始化策略"""
        # 保存初始资金
        self.initial_value = self.broker.getvalue()

        # 创建均线指标
        if self.p.ma_type == 'SMA':
            self.ma = bt.ind.SMA(self.data.close, period=self.p.ma_period)
        elif self.p.ma_type == 'EMA':
            self.ma = bt.ind.EMA(self.data.close, period=self.p.ma_period)
        else:
            raise ValueError(f"不支持的均线类型: {self.p.ma_type}")

        # 创建交叉信号指标
        self.crossover = bt.ind.CrossOver(self.data.close, self.ma)

        # 订单变量
        self.order = None
        self.buy_price = None
        self.buy_comm = None

        # 止损止盈价格
        self.stop_price = None
        self.target_price = None

        # 交易计数
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0

        # 打印初始化信息
        if self.p.printlog:
            self.log(f'策略初始化完成 - 均线周期: {self.p.ma_period}, '
                    f'类型: {self.p.ma_type}, '
                    f'止损: {self.p.stop_loss*100}%, '
                    f'止盈: {self.p.take_profit*100}%')

    def log(self, txt, dt=None):
        """日志函数"""
        if self.p.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'[{dt.isoformat()}] {txt}')

    def notify_order(self, order):
        """订单状态通知"""
        if order.status in [order.Submitted, order.Accepted]:
            # 订单已提交/已接受 - 不做任何操作
            return

        # 检查订单是否完成
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'买入执行 - 价格: {order.executed.price:.2f}, '
                        f'成本: {order.executed.value:.2f}, '
                        f'手续费: {order.executed.comm:.2f}')
                self.buy_price = order.executed.price
                self.buy_comm = order.executed.comm

                # 设置止损止盈价格
                self.stop_price = order.executed.price * (1 - self.p.stop_loss)
                self.target_price = order.executed.price * (1 + self.p.take_profit)

                self.log(f'止损价: {self.stop_price:.2f}, 止盈价: {self.target_price:.2f}')

            else:
                self.log(f'卖出执行 - 价格: {order.executed.price:.2f}, '
                        f'成本: {order.executed.value:.2f}, '
                        f'手续费: {order.executed.comm:.2f}')

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('订单取消/保证金不足/拒绝')

        # 清空订单
        self.order = None

    def notify_trade(self, trade):
        """交易完成通知"""
        if not trade.isclosed:
            return

        self.trade_count += 1
        pnl = trade.pnl
        pnlcomm = trade.pnlcomm

        if pnlcomm > 0:
            self.win_count += 1
            result = '盈利'
        else:
            self.loss_count += 1
            result = '亏损'

        self.log(f'交易#{self.trade_count} {result} - '
                f'毛利润: {pnl:.2f}, 净利润: {pnlcomm:.2f}')

    def next(self):
        """策略主逻辑 - 每个bar执行一次"""

        # 检查是否有未完成订单
        if self.order:
            return

        # 获取当前价格和均线值
        current_price = self.data.close[0]
        ma_value = self.ma[0]

        # 检查是否持仓
        if not self.position:
            # 无持仓 - 检查买入信号

            # 价格上穿均线，买入信号
            if self.crossover > 0:
                # 计算买入数量（使用百分比仓位）
                cash = self.broker.getcash()
                position_size = (cash * self.p.position_pct) / current_price

                # 执行买入
                self.log(f'买入信号 - 价格: {current_price:.2f}, '
                        f'均线: {ma_value:.2f}, '
                        f'计划买入: {int(position_size)}股')
                self.order = self.buy(size=int(position_size))

        else:
            # 有持仓 - 检查卖出信号

            # 情况1：价格下穿均线，卖出信号
            if self.crossover < 0:
                self.log(f'卖出信号(均线交叉) - 价格: {current_price:.2f}, '
                        f'均线: {ma_value:.2f}')
                self.order = self.sell()

            # 情况2：触发止损
            elif current_price <= self.stop_price:
                self.log(f'止损触发 - 价格: {current_price:.2f}, '
                        f'止损价: {self.stop_price:.2f}')
                self.order = self.sell()

            # 情况3：触发止盈
            elif current_price >= self.target_price:
                self.log(f'止盈触发 - 价格: {current_price:.2f}, '
                        f'止盈价: {self.target_price:.2f}')
                self.order = self.sell()

    def stop(self):
        """策略结束时调用"""
        # 计算最终收益
        final_value = self.broker.getvalue()
        pnl = final_value - self.initial_value
        pnl_pct = (pnl / self.initial_value) * 100

        # 打印总结
        self.log('=' * 60)
        self.log('策略执行总结')
        self.log('=' * 60)
        self.log(f'初始资金: {self.initial_value:.2f}')
        self.log(f'最终资金: {final_value:.2f}')
        self.log(f'总收益: {pnl:.2f} ({pnl_pct:.2f}%)')
        self.log(f'总交易次数: {self.trade_count}')
        self.log(f'盈利次数: {self.win_count}')
        self.log(f'亏损次数: {self.loss_count}')

        if self.trade_count > 0:
            win_rate = (self.win_count / self.trade_count) * 100
            self.log(f'胜率: {win_rate:.2f}%')

        self.log('=' * 60)


class MovingAverageFollowingSimple(bt.Strategy):
    """简化版均线跟随策略（用于快速测试）"""

    params = (
        ('ma_period', 20),
        ('printlog', False),
    )

    def __init__(self):
        self.ma = bt.ind.SMA(period=self.p.ma_period)
        self.crossover = bt.ind.CrossOver(self.data.close, self.ma)

    def next(self):
        if not self.position:
            if self.crossover > 0:
                self.buy()
        else:
            if self.crossover < 0:
                self.sell()


if __name__ == '__main__':
    # 测试策略类
    print("均线跟随策略定义文件")
    print("请在主程序中导入使用")
