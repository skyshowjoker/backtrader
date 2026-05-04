# 均线跟随策略 - 完整流程演示

## 项目概述

本项目演示了如何使用 Backtrader 框架创建一个完整的均线跟随策略，包括策略开发、回测执行、性能分析和结果可视化。

## 文件结构

```
backtrader/
├── strategies/
│   └── ma_following.py          # 均线跟随策略实现
├── main.py                       # 主程序（回测执行）
├── datas/
│   └── orcl-1995-2014.txt       # Oracle股票历史数据
└── doc/
    ├── 01_项目结构分析.md
    ├── 02_使用说明.md
    ├── 03_开发指导.md
    ├── 04_架构图解.md
    └── README.md
```

## 策略说明

### 策略逻辑

**均线跟随策略 (Moving Average Following Strategy)**

1. **买入信号**: 价格上穿均线时买入
2. **卖出信号**: 价格下穿均线时卖出
3. **止损机制**: 价格下跌5%触发止损
4. **止盈机制**: 价格上涨10%触发止盈
5. **仓位管理**: 使用95%的资金买入

### 策略参数

```python
params = (
    ('ma_period', 20),           # 均线周期：20日
    ('ma_type', 'SMA'),          # 均线类型：简单移动平均
    ('stop_loss', 0.05),         # 止损比例：5%
    ('take_profit', 0.10),       # 止盈比例：10%
    ('position_pct', 0.95),      # 仓位比例：95%
    ('printlog', False),         # 是否打印日志
)
```

## 运行流程

### 1. 策略开发

策略文件位于 `strategies/ma_following.py`，包含：

- **完整版策略**: `MovingAverageFollowing` - 包含详细的日志和统计
- **简化版策略**: `MovingAverageFollowingSimple` - 用于快速测试和参数优化

### 2. 回测配置

主程序 `main.py` 包含完整的回测流程：

```python
# 1. 创建Cerebro引擎
cerebro = bt.Cerebro(stdstats=True, preload=True, runonce=True)

# 2. 配置资金和佣金
cerebro.broker.setcash(100000.0)  # 初始资金10万
cerebro.broker.setcommission(0.001)  # 0.1%佣金

# 3. 添加数据源
data = bt.feeds.YahooFinanceCSVData(
    dataname='datas/orcl-1995-2014.txt',
    fromdate=datetime(2000, 1, 1),
    todate=datetime(2014, 12, 31)
)

# 4. 添加策略
cerebro.addstrategy(MovingAverageFollowing)

# 5. 添加分析器
cerebro.addanalyzer(bt.analyzers.SharpeRatio)
cerebro.addanalyzer(bt.analyzers.DrawDown)
cerebro.addanalyzer(bt.analyzers.Returns)

# 6. 执行回测
results = cerebro.run()
```

### 3. 运行回测

```bash
# 运行回测
python main.py --mode backtest

# 运行参数优化
python main.py --mode optimize
```

### 4. 分析结果

回测完成后，系统会输出详细的性能分析报告：

- **基础信息**: 初始资金、最终资金、总收益
- **风险指标**: 夏普比率、最大回撤
- **收益指标**: 总收益率、平均收益率、年化收益
- **交易统计**: 总交易次数、盈利次数、亏损次数、胜率、盈亏比

## 预期结果

基于Oracle股票2000-2014年的数据，策略预期表现：

- **数据范围**: 2000-01-01 到 2014-12-31 (15年)
- **初始资金**: 100,000元
- **交易频率**: 高频交易（由于止损止盈机制）
- **风险控制**: 5%止损 + 10%止盈

## 关键特性

### 1. 完整的日志系统

策略包含详细的交易日志：
- 买入/卖出信号
- 订单执行价格和成本
- 止损/止盈触发
- 交易盈亏统计

### 2. 多种分析器

- **SharpeRatio**: 夏普比率（风险调整后收益）
- **DrawDown**: 最大回撤分析
- **Returns**: 收益率分析
- **TradeAnalyzer**: 交易统计
- **AnnualReturn**: 年化收益

### 3. 参数优化支持

支持多进程参数优化：
```bash
python main.py --mode optimize
```

测试不同的均线周期（10, 15, 20, 25, 30），找出最佳参数组合。

### 4. 可视化支持

支持matplotlib绘图：
- 价格走势图
- 均线指标
- 买卖点标记
- 资金曲线

## 学习要点

### 1. 策略生命周期

```
初始化 (__init__)
  ↓
预热阶段 (prenext)
  ↓
第一次有效数据 (nextstart)
  ↓
主循环 (next) ← 每个bar执行一次
  ↓
订单通知 (notify_order)
  ↓
交易通知 (notify_trade)
  ↓
结束 (stop)
```

### 2. 核心概念

- **LineBuffer**: 存储时间序列数据的核心数据结构
- **Indicator**: 技术指标，自动处理数据对齐
- **Order**: 订单管理系统
- **Position**: 持仓管理
- **Analyzer**: 性能分析工具

### 3. 最佳实践

- 使用参数系统管理策略参数
- 实现完整的订单和交易通知
- 添加止损止盈机制控制风险
- 使用分析器评估策略性能
- 支持参数优化寻找最佳配置

## 扩展建议

### 1. 策略改进

- 添加更多指标（RSI、MACD、布林带等）
- 实现动态止损止盈
- 添加市场环境过滤
- 支持多数据源、多时间框架

### 2. 风险管理

- 实现最大回撤限制
- 添加仓位集中度控制
- 支持动态仓位管理
- 实现连续亏损保护

### 3. 实盘交易

- 集成Interactive Brokers
- 集成Oanda API
- 实现实时数据订阅
- 添加异常处理和恢复机制

## 参考文档

详细文档请查看 `doc/` 目录：

1. **01_项目结构分析.md** - Backtrader架构详解
2. **02_使用说明.md** - 完整使用手册
3. **03_开发指导.md** - 开发者指南
4. **04_架构图解.md** - 可视化架构图

## 常见问题

### Q: 为什么有这么多交易记录？

A: 策略使用了5%止损和10%止盈机制，导致高频交易。可以调整参数减少交易频率。

### Q: 如何修改策略参数？

A: 在 `main.py` 中修改 `cerebro.addstrategy()` 的参数，或在策略文件中修改默认参数。

### Q: 如何使用其他数据？

A: 支持多种数据源：
- Yahoo Finance在线数据
- Pandas DataFrame
- CSV文件
- 实盘数据（IB、Oanda）

### Q: 如何添加更多指标？

A: 在策略的 `__init__()` 方法中创建指标：
```python
self.rsi = bt.ind.RSI(period=14)
self.macd = bt.ind.MACD()
```

## 下一步

1. 运行回测查看完整结果
2. 尝试参数优化寻找最佳配置
3. 修改策略添加新功能
4. 测试不同的数据源和时间范围
5. 开发自己的交易策略

---

**提示**: 这是一个完整的策略开发示例，可以作为开发其他策略的模板。详细使用说明请参考 `doc/` 目录下的文档。