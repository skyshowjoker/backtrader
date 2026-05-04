#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
"""
均线跟随策略 - 主程序
完整的回测流程演示
"""

from datetime import datetime
import backtrader as bt
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入策略
from strategies.ma_following import MovingAverageFollowing, MovingAverageFollowingSimple


def run_backtest():
    """运行回测"""

    print('=' * 80)
    print('均线跟随策略 - 回测系统')
    print('=' * 80)
    print()

    # ========== 1. 创建Cerebro引擎 ==========
    print('步骤1: 创建Cerebro引擎...')
    cerebro = bt.Cerebro(
        stdstats=True,      # 添加默认观察者
        preload=True,       # 预加载数据
        runonce=True,       # 向量化模式
    )

    # ========== 2. 设置初始资金和佣金 ==========
    print('步骤2: 配置初始资金和佣金...')
    initial_cash = 100000.0  # 初始资金10万
    cerebro.broker.setcash(initial_cash)

    # 设置佣金
    cerebro.broker.setcommission(
        commission=0.001,     # 0.1% 佣金
        margin=None,
        mult=1.0
    )

    # 设置滑点
    cerebro.broker.set_slippage_perc(
        perc=0.0001,          # 0.01% 滑点
        slip_open=True,
        slip_limit=True,
        slip_match=True,
        slip_out=False
    )

    print(f'  - 初始资金: {initial_cash:.2f}')
    print(f'  - 佣金比例: 0.1%')
    print(f'  - 滑点比例: 0.01%')
    print()

    # ========== 3. 添加数据源 ==========
    print('步骤3: 添加数据源...')

    # 方式1: 使用本地CSV数据（推荐，稳定可靠）
    # 使用Backtrader自带的示例数据
    csv_file = 'datas/orcl-1995-2014.txt'  # Oracle股票数据
    if os.path.exists(csv_file):
        data = bt.feeds.YahooFinanceCSVData(
            dataname=csv_file,
            fromdate=datetime(2000, 1, 1),
            todate=datetime(2014, 12, 31),
            reverse=False
        )
        cerebro.adddata(data)
        print(f'  - 数据源: 本地CSV ({csv_file})')
        print('  - 时间范围: 2000-01-01 到 2014-12-31')
        data_source = '本地CSV'
    else:
        print('  - 错误: 未找到数据文件')
        print('  - 请确保 datas/orcl-1995-2014.txt 文件存在')
        return None

    print()

    # ========== 4. 添加策略 ==========
    print('步骤4: 添加策略...')

    # 使用完整版策略
    cerebro.addstrategy(
        MovingAverageFollowing,
        ma_period=20,           # 20日均线
        ma_type='SMA',          # 简单移动平均
        stop_loss=0.05,         # 5%止损
        take_profit=0.10,       # 10%止盈
        position_pct=0.95,      # 95%仓位
        printlog=True
    )

    print('  - 策略: 均线跟随策略')
    print('  - 参数: 20日SMA, 5%止损, 10%止盈')
    print()

    # ========== 5. 添加分析器 ==========
    print('步骤5: 添加分析器...')

    # 夏普比率
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')

    # 收益率分析
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')

    # 回撤分析
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')

    # 交易分析
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    # 年化收益
    cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name='annual_return')

    print('  - 夏普比率分析器')
    print('  - 收益率分析器')
    print('  - 回撤分析器')
    print('  - 交易分析器')
    print('  - 年化收益分析器')
    print()

    # ========== 6. 添加观察者 ==========
    print('步骤6: 添加观察者...')
    cerebro.addobserver(bt.observers.Broker)
    cerebro.addobserver(bt.observers.Trades)
    cerebro.addobserver(bt.observers.BuySell)

    print('  - 经纪人观察者')
    print('  - 交易观察者')
    print('  - 买卖点观察者')
    print()

    # ========== 7. 执行回测 ==========
    print('步骤7: 执行回测...')
    print('-' * 80)

    # 记录开始时间
    import time
    start_time = time.time()

    # 运行回测
    results = cerebro.run()

    # 计算耗时
    elapsed_time = time.time() - start_time

    # 获取策略实例
    strategy = results[0]

    print('-' * 80)
    print(f'回测完成! 耗时: {elapsed_time:.2f}秒')
    print()

    # ========== 8. 分析结果 ==========
    print('步骤8: 分析回测结果...')
    print('=' * 80)

    # 获取分析结果
    sharpe_analysis = strategy.analyzers.sharpe.get_analysis()
    returns_analysis = strategy.analyzers.returns.get_analysis()
    drawdown_analysis = strategy.analyzers.drawdown.get_analysis()
    trades_analysis = strategy.analyzers.trades.get_analysis()
    annual_return_analysis = strategy.analyzers.annual_return.get_analysis()

    # 打印详细分析报告
    print('\n' + '=' * 80)
    print('回测分析报告')
    print('=' * 80)

    # 1. 基础信息
    print('\n【基础信息】')
    print(f'数据源: {data_source}')
    print(f'初始资金: {initial_cash:,.2f}')
    final_value = cerebro.broker.getvalue()
    print(f'最终资金: {final_value:,.2f}')

    pnl = final_value - initial_cash
    pnl_pct = (pnl / initial_cash) * 100
    print(f'总收益: {pnl:,.2f} ({pnl_pct:.2f}%)')

    # 2. 风险指标
    print('\n【风险指标】')
    sharpe_ratio = sharpe_analysis.get('sharperatio', None)
    if sharpe_ratio is not None:
        print(f'夏普比率: {sharpe_ratio:.4f}')
    else:
        print('夏普比率: N/A')

    max_drawdown = drawdown_analysis.get('max', {}).get('drawdown', 0)
    max_drawdown_len = drawdown_analysis.get('max', {}).get('len', 0)
    print(f'最大回撤: {max_drawdown:.2f}%')
    print(f'最大回撤持续期: {max_drawdown_len} 天')

    # 3. 收益指标
    print('\n【收益指标】')
    total_return = returns_analysis.get('rtot', 0)
    average_return = returns_analysis.get('ravg', 0)
    print(f'总收益率: {total_return * 100:.2f}%')
    print(f'平均收益率: {average_return * 100:.4f}%')

    # 年化收益
    print('\n【年化收益】')
    for year, return_val in sorted(annual_return_analysis.items()):
        print(f'{year}: {return_val * 100:.2f}%')

    # 4. 交易统计
    print('\n【交易统计】')
    total_trades = trades_analysis.get('total', {}).get('total', 0)
    won_trades = trades_analysis.get('won', {}).get('total', 0)
    lost_trades = trades_analysis.get('lost', {}).get('total', 0)

    print(f'总交易次数: {total_trades}')
    print(f'盈利次数: {won_trades}')
    print(f'亏损次数: {lost_trades}')

    if total_trades > 0:
        win_rate = (won_trades / total_trades) * 100
        print(f'胜率: {win_rate:.2f}%')

        # 平均盈亏
        if won_trades > 0:
            avg_won = trades_analysis.get('won', {}).get('pnl', {}).get('average', 0)
            print(f'平均盈利: {avg_won:.2f}')

        if lost_trades > 0:
            avg_lost = trades_analysis.get('lost', {}).get('pnl', {}).get('average', 0)
            print(f'平均亏损: {abs(avg_lost):.2f}')

        # 盈亏比
        if lost_trades > 0 and won_trades > 0:
            avg_won = trades_analysis.get('won', {}).get('pnl', {}).get('average', 1)
            avg_lost = abs(trades_analysis.get('lost', {}).get('pnl', {}).get('average', 1))
            profit_loss_ratio = avg_won / avg_lost if avg_lost != 0 else 0
            print(f'盈亏比: {profit_loss_ratio:.2f}')

    print('\n' + '=' * 80)

    # ========== 9. 绘图 ==========
    print('\n步骤9: 生成图表...')
    try:
        # 检查matplotlib是否可用
        import matplotlib.pyplot as plt

        print('正在生成图表...')
        print('提示: 图表将在新窗口中显示，关闭图表窗口后程序继续执行')

        # 绘制结果
        fig = cerebro.plot(
            style='candle',       # 蜡烛图
            barup='red',          # 上涨红色
            bardown='green',      # 下跌绿色
            volume=True,          # 显示成交量
            grid=True,            # 显示网格
            figsize=(20, 10),     # 图表大小
            dpi=100,              # 分辨率
            tight=True,           # 紧凑布局
        )

        # 保存图片
        output_dir = 'output'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        output_file = os.path.join(output_dir, 'backtest_result.png')
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f'图表已保存: {output_file}')

        # 显示图表
        plt.show()

    except ImportError:
        print('警告: matplotlib未安装，跳过绘图步骤')
        print('安装方法: pip install matplotlib')
    except Exception as e:
        print(f'绘图错误: {e}')

    print('\n' + '=' * 80)
    print('回测流程完成!')
    print('=' * 80)

    return results


def run_optimization():
    """运行参数优化"""

    print('=' * 80)
    print('均线跟随策略 - 参数优化')
    print('=' * 80)
    print()

    # 创建Cerebro
    cerebro = bt.Cerebro(maxcpus=4)  # 使用4个CPU核心

    # 设置资金
    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.001)

    # 添加数据
    try:
        data = bt.feeds.YahooFinanceData(
            dataname='AAPL',
            fromdate=datetime(2020, 1, 1),
            todate=datetime(2023, 12, 31),
        )
        cerebro.adddata(data)
    except:
        csv_file = 'datas/orcl-1995-2014.txt'
        if os.path.exists(csv_file):
            data = bt.feeds.YahooFinanceCSVData(
                dataname=csv_file,
                fromdate=datetime(2000, 1, 1),
                todate=datetime(2014, 12, 31),
            )
            cerebro.adddata(data)

    # 添加策略优化参数
    cerebro.optstrategy(
        MovingAverageFollowingSimple,
        ma_period=range(10, 31, 5),  # 测试10, 15, 20, 25, 30
    )

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')

    # 运行优化
    print('运行参数优化...')
    results = cerebro.run()

    # 分析结果
    print('\n优化结果:')
    print('-' * 80)
    print(f'{"参数":<15} {"夏普比率":<15} {"总收益率":<15}')
    print('-' * 80)

    for result in results:
        strategy = result[0]
        params = strategy.params
        sharpe = strategy.analyzers.sharpe.get_analysis().get('sharperatio', 0)
        returns = strategy.analyzers.returns.get_analysis().get('rtot', 0)

        print(f'{params.ma_period:<15} {sharpe:<15.4f} {returns*100:<15.2f}%')

    print('-' * 80)

    # 找出最佳参数
    best_result = max(results, key=lambda r:
                     r[0].analyzers.sharpe.get_analysis().get('sharperatio', 0) or 0)

    best_strategy = best_result[0]
    best_params = best_strategy.params
    best_sharpe = best_strategy.analyzers.sharpe.get_analysis().get('sharperatio', 0)
    best_return = best_strategy.analyzers.returns.get_analysis().get('rtot', 0)

    print(f'\n最佳参数: ma_period = {best_params.ma_period}')
    print(f'夏普比率: {best_sharpe:.4f}')
    print(f'总收益率: {best_return*100:.2f}%')
    print('=' * 80)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='均线跟随策略回测系统')
    parser.add_argument('--mode', type=str, default='backtest',
                       choices=['backtest', 'optimize'],
                       help='运行模式: backtest(回测) 或 optimize(优化)')

    args = parser.parse_args()

    if args.mode == 'backtest':
        run_backtest()
    elif args.mode == 'optimize':
        run_optimization()
