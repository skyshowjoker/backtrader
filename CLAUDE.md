# Backtrader 项目 - Claude AI 助手指南

## 项目概述

这是 **Backtrader** 项目，一个功能强大的 Python 回测和实盘交易框架。

- **版本**: 1.9.78.123
- **语言**: Python 3.2+
- **许可证**: GPLv3+
- **核心特点**: 自包含、无外部依赖（绘图功能需要matplotlib）

## 项目结构

```
backtrader/
├── backtrader/              # 核心源码（171个Python文件）
│   ├── cerebro.py          # 核心引擎
│   ├── strategy.py         # 策略基类
│   ├── feed.py             # 数据源基类
│   ├── indicator.py        # 指标基类
│   ├── analyzers/          # 分析器（夏普比率、回撤等）
│   ├── indicators/         # 内置指标库（122个指标）
│   ├── feeds/              # 数据源实现（Yahoo、Pandas、CSV等）
│   ├── brokers/            # 经纪人实现（回测、IB、Oanda）
│   └── ...
├── samples/                 # 示例代码（70个示例）
├── tests/                   # 测试用例
├── doc/                     # 项目文档（已创建）
└── setup.py                 # 安装配置
```

## 核心概念

### 1. Cerebro（引擎）
整个系统的控制中心，负责协调所有组件。

### 2. Strategy（策略）
交易逻辑的核心，继承 `bt.Strategy` 类，实现 `__init__()` 和 `next()` 方法。

### 3. Data Feeds（数据源）
提供历史和实时数据，支持多种格式（Yahoo、Pandas、CSV、IB、Oanda等）。

### 4. Indicators（指标）
122个内置技术指标，支持自定义指标开发。

### 5. Analyzers（分析器）
计算策略性能指标（夏普比率、最大回撤、交易统计等）。

### 6. Brokers（经纪人）
模拟真实交易环境，处理订单执行、佣金、滑点。

## 快速开始示例

```python
from datetime import datetime
import backtrader as bt

class SmaCross(bt.SignalStrategy):
    def __init__(self):
        sma1 = bt.ind.SMA(period=10)
        sma2 = bt.ind.SMA(period=30)
        crossover = bt.ind.CrossOver(sma1, sma2)
        self.signal_add(bt.SIGNAL_LONG, crossover)

cerebro = bt.Cerebro()
cerebro.addstrategy(SmaCross)

data = bt.feeds.YahooFinanceData(dataname='MSFT',
                                 fromdate=datetime(2020, 1, 1),
                                 todate=datetime(2021, 12, 31))
cerebro.adddata(data)

cerebro.run()
cerebro.plot()
```

## 开发规范

### 策略开发模板

```python
class MyStrategy(bt.Strategy):
    params = (
        ('param1', 10),
        ('printlog', True),
    )

    def __init__(self):
        # 初始化指标
        self.indicator = bt.ind.SMA(period=self.p.param1)
        self.order = None

    def next(self):
        # 核心交易逻辑
        if not self.position:
            if self.data.close[0] > self.indicator[0]:
                self.order = self.buy()
        else:
            if self.data.close[0] < self.indicator[0]:
                self.order = self.sell()

    def notify_order(self, order):
        # 订单状态通知
        if order.status in [order.Completed]:
            if self.p.printlog:
                print(f'订单执行: {order.executed.price}')

    def notify_trade(self, trade):
        # 交易通知
        if trade.isclosed:
            print(f'交易盈亏: {trade.pnl}')
```

### 自定义指标模板

```python
class MyIndicator(bt.Indicator):
    lines = ('signal',)
    params = (('period', 20),)

    def __init__(self):
        self.lines.signal = bt.ind.SMA(self.data.close, period=self.p.period)

    # 或者使用 next() 方法
    def next(self):
        self.lines.signal[0] = sum(self.data.close.get(size=self.p.period)) / self.p.period
```

## 常用操作

### 添加数据源

```python
# Yahoo Finance
data = bt.feeds.YahooFinanceData(dataname='AAPL', fromdate=..., todate=...)

# Pandas DataFrame
data = bt.feeds.PandasData(dataname=df)

# CSV文件
data = bt.feeds.GenericCSVData(dataname='data.csv')
```

### 添加分析器

```python
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')

results = cerebro.run()
strategy = results[0]

sharpe = strategy.analyzers.sharpe.get_analysis()
drawdown = strategy.analyzers.drawdown.get_analysis()
```

### 参数优化

```python
cerebro.optstrategy(MyStrategy,
                    period=range(10, 31, 5),
                    threshold=[0.3, 0.5, 0.7])

results = cerebro.run(maxcpus=4)
```

## 重要文件位置

- **核心引擎**: `backtrader/cerebro.py`
- **策略基类**: `backtrader/strategy.py`
- **数据源**: `backtrader/feeds/`
- **指标库**: `backtrader/indicators/`
- **示例代码**: `samples/`
- **测试用例**: `tests/`
- **项目文档**: `doc/`

## 文档资源

项目已创建完整的中文文档，位于 `doc/` 目录：

1. **README.md** - 文档索引和导航
2. **01_项目结构分析.md** - 详细的项目结构分析
3. **02_使用说明.md** - 完整的用户手册
4. **03_开发指导.md** - 开发者指南
5. **04_架构图解.md** - 架构和流程图解

## 测试

运行测试：
```bash
python -m pytest tests/
```

## 安装

```bash
# 从源码安装
python setup.py install

# 或使用pip
pip install -e .
```

## 注意事项

1. **数据访问**: 使用索引访问数据，如 `self.data.close[0]` (当前)、`self.data.close[-1]` (前一个)
2. **订单管理**: 在 `next()` 中检查 `self.order` 避免重复下单
3. **指标预热**: 数据不足时调用 `prenext()`，需要处理或等待
4. **性能优化**: 使用 `runonce=True` 启用向量化模式
5. **内存管理**: 大数据集使用 `preload=False` 或 `exactbars=True`

## 关键设计模式

1. **元类系统**: 用于参数自动收集和管理
2. **线条缓冲区**: LineBuffer 是核心数据结构，存储时间序列
3. **迭代器模式**: Strategy、Indicator 都继承自 LineIterator
4. **观察者模式**: Observers 用于实时观察策略状态
5. **策略模式**: 支持多种订单类型、佣金方案、滑点模型

## 扩展点

- 自定义策略：继承 `bt.Strategy`
- 自定义指标：继承 `bt.Indicator`
- 自定义分析器：继承 `bt.Analyzer`
- 自定义数据源：继承 `bt.feeds.DataBase`
- 自定义经纪人：继承 `bt.brokers.BackBroker`
- 自定义仓位管理器：继承 `bt.Sizer`

## 实盘交易支持

- **Interactive Brokers**: 使用 `bt.stores.IBStore` 和 `bt.brokers.IBBroker`
- **Oanda**: 使用 `bt.stores.OandaStore` 和 `bt.brokers.Oandabroker`
- **Visual Chart**: 使用 `bt.stores.VCStore` 和 `bt.brokers.VCBroker`

## 常见问题

### Q: 如何处理数据不足？
A: 实现 `prenext()` 方法，或检查 `len(self.data) >= self.p.period`

### Q: 如何获取持仓信息？
A: 使用 `self.getposition()` 或 `self.position.size`

### Q: 如何设置佣金？
A: `cerebro.broker.setcommission(commission=0.001)` 或自定义佣金方案

### Q: 如何启用绘图？
A: 安装 matplotlib，然后调用 `cerebro.plot()`

## 代码风格

- 遵循 PEP 8 规范
- 使用有意义的参数名
- 添加适当的日志和注释
- 实现错误处理
- 编写单元测试

## 参考资源

- 官方文档: http://www.backtrader.com/docu
- 社区论坛: https://community.backtrader.com
- GitHub: https://github.com/mementum/backtrader

---

**提示**: 在帮助用户时，优先参考 `doc/` 目录下的文档，其中包含详细的说明和示例。对于架构相关问题，参考 `doc/04_架构图解.md`。
