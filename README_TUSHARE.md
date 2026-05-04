# Tushare 数据对接方案

本项目已成功对接 `/Users/mac/Downloads/行情数据` 中的 Tushare Parquet 格式数据到 Backtrader 回测框架。

## 快速开始

### 1. 最简单的示例

```python
from tushare_data_loader import TushareDataLoader
import backtrader as bt

# 加载数据
loader = TushareDataLoader('/Users/mac/Downloads/行情数据')
data = loader.load_daily_data('000001.SZ', '2023-01-01', '2023-12-31')

# 运行回测
cerebro = bt.Cerebro()
cerebro.adddata(data)
cerebro.addstrategy(MyStrategy)
cerebro.run()
```

### 2. 运行示例

```bash
# 快速开始
python quick_start.py

# 完整示例
python example_backtest.py

# 数据浏览
python data_browser.py
```

## 核心文件

| 文件 | 说明 |
|------|------|
| `tushare_data_loader.py` | 数据加载器(核心) |
| `example_backtest.py` | 完整回测示例 |
| `quick_start.py` | 快速开始示例 |
| `data_browser.py` | 数据浏览工具 |
| `数据对接指南.md` | 详细使用文档 |
| `数据对接完成总结.md` | 完成总结 |

## 数据说明

### 日线数据
- **股票数**: 5,767 只
- **时间范围**: 2009-01-05 至 2026-04-17
- **字段**: 31个(行情、估值、停牌等)

### 分钟线数据
- **周期**: 1min, 15min, 30min, 60min
- **股票数**: 5,767 只
- **字段**: 8个(行情 + 复权因子)

## 主要功能

### ✅ 数据加载
- 日线数据加载
- 分钟线数据加载(1/15/30/60分钟)
- 自动复权处理(后复权/前复权/不复权)
- 日期范围筛选
- 多股票支持

### ✅ 回测功能
- 策略回测
- 参数优化
- 多股票回测
- 分析器支持(夏普比率、回撤等)

### ✅ 数据浏览
- 数据概览
- 股票列表
- 数据检查
- 股票搜索

## 使用示例

### 日线回测

```python
loader = TushareDataLoader()
data = loader.load_daily_data(
    ts_code='000001.SZ',
    start_date='2020-01-01',
    end_date='2023-12-31',
    adj_type='hfq'  # 后复权
)
```

### 分钟线回测

```python
data = loader.load_minute_data(
    ts_code='000001.SZ',
    freq='15min',
    start_date='2023-06-01',
    end_date='2023-06-30',
    adj_type='qfq'  # 前复权
)
```

### 多股票回测

```python
stocks = ['000001.SZ', '000002.SZ', '600000.SH']
for stock in stocks:
    data = loader.load_daily_data(stock, '2022-01-01', '2023-12-31')
    cerebro.adddata(data)
```

## 文档

详细使用说明请参考:
- **数据对接指南.md** - 完整的使用文档
- **数据对接完成总结.md** - 功能总结
- **doc/** 目录 - Backtrader 官方文档

## 测试状态

✅ 所有功能已测试通过:
- 数据加载正常
- 复权处理正确
- 回测运行成功
- 分析器工作正常

---

**数据路径**: `/Users/mac/Downloads/行情数据`
**对接日期**: 2026-05-02
**状态**: ✅ 完成
