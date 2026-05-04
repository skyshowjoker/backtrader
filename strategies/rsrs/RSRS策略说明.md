# RSRS价值选股策略说明

## 策略来源

克隆自聚宽文章：https://www.joinquant.com/post/15002
标题：价值选股与RSRS择时
作者：K线放荡不羁

## 策略思路

### 1. 选股逻辑（价值选股）
- 基于财务指标选股
- 筛选条件：PB > 0 且 ROE > 0
- 排序方法：
  - 按PB升序排列
  - 对PB和1/ROE进行排名
  - 综合得分 = PB排名 + 1/ROE排名
  - 选择得分最低的10只股票

### 2. 择时逻辑（RSRS指标）
RSRS（Resistance Support Relative Strength）阻力支撑相对强度指标

#### 计算方法：
1. 对过去N天的高低价进行线性回归：
   ```
   high = alpha + beta * low
   ```

2. 计算标准化RSRS指标：
   - 取最近M个beta值
   - 计算均值μ和标准差σ
   - zscore = (beta - μ) / σ

3. 计算右偏RSRS标准分：
   ```
   zscore_rightdev = zscore * beta * R²
   ```
   其中R²是回归的决定系数

#### 交易信号：
- **买入信号**: zscore_rightdev > 0.7
- **卖出信号**: zscore_rightdev < -0.7

### 3. 持仓管理
- 满足买入条件时：持有选出的10只股票
- 满足卖出条件时：清仓
- 资金分配：等权重分配

## 参数设置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| rsrs_period (N) | 18 | RSRS统计周期 |
| rsrs_sample (M) | 1100 | RSRS样本长度 |
| buy_threshold | 0.7 | 买入阈值 |
| sell_threshold | -0.7 | 卖出阈值 |
| stock_num | 10 | 持仓股票数量 |

## 实现文件

### 1. rsrc_strategy.py
核心策略实现，包含：
- `RSRSIndicator`: RSRS指标计算类
- `ValueSelection`: 价值选股工具类
- `RSRSStrategy`: 单股票RSRS策略
- `RSRSStrategyMultiStock`: 多股票RSRS策略

### 2. rsrc_backtest.py
回测脚本，包含：
- `run_rsrc_backtest_simple()`: 简化版回测（指数择时）
- `run_rsrc_backtest_multistock()`: 多股票版回测
- `test_rsrs_indicator()`: RSRS指标测试

## 使用方法

### 1. 简化版回测（推荐先测试）
```bash
python rsrc_backtest.py 1
```
使用指数作为标的，测试RSRS择时效果

### 2. 多股票版回测
```bash
python rsrc_backtest.py 2
```
完整的策略实现，包含选股和择时

### 3. 测试RSRS指标
```bash
python rsrc_backtest.py 3
```
可视化RSRS指标，验证计算逻辑

## 策略特点

### 优点
1. **市场择时能力强**: RSRS指标能有效判断市场风险
2. **价值投资导向**: 选股逻辑偏向低估值高质量股票
3. **风险控制**: 及时清仓规避市场风险
4. **逻辑清晰**: 择时和选股分离，易于理解和改进

### 缺点
1. **数据要求高**: 需要足够的历史数据计算RSRS
2. **参数敏感**: 不同参数对结果影响较大
3. **交易频率**: 可能产生较多的交易信号
4. **选股简化**: 当前实现简化了选股逻辑

## 回测结果示例

### 简化版（指数择时）
- 时间范围：2010-2023
- 初始资金：100万
- 策略表现：
  - 成功捕捉2014-2015年牛市
  - 2015年股灾前及时清仓
  - 规避了多次市场大跌

### 典型交易记录
```
2014-11-26: 市场风险合理,RSRS=1.6660
买入执行: 价格 806.46

2015-05-04: 市场风险过大,清仓,RSRS=-0.8758
卖出执行: 价格 1411.16
交易完成: 毛利 604.70, 净利 602.48
```

## 改进方向

### 1. 选股优化
- 添加更多财务指标（如ROA、现金流等）
- 行业中性处理
- 动态调整持仓数量

### 2. 择时优化
- 调整RSRS参数
- 添加其他择时指标验证
- 分批建仓/平仓

### 3. 风险管理
- 添加止损机制
- 最大回撤控制
- 波动率调整仓位

### 4. 交易成本
- 考虑滑点
- 优化交易频率
- 换手率控制

## 技术要点

### 1. RSRS指标计算
```python
# 线性回归
X = sm.add_constant(lows)
model = sm.OLS(highs, X)
results = model.fit()
beta = results.params[1]  # 斜率
r2 = results.rsquared      # R²

# 标准化
zscore = (beta - mu) / sigma

# 右偏修正
zscore_rightdev = zscore * beta * r2
```

### 2. 价值选股
```python
# 筛选
df = df[(df['pb'] > 0) & (df['roe'] > 0)]

# 排名打分
df['pb_rank'] = df['pb'].rank()
df['roe_rank'] = (1 / df['roe']).rank()
df['score'] = df['pb_rank'] + df['roe_rank']

# 选股
selected = df.nsmallest(10, 'score')
```

## 注意事项

1. **数据准备**: 需要股票基础数据（PB、ROE等）
2. **计算时间**: RSRS指标需要较长的历史数据
3. **内存占用**: 多股票回测注意内存管理
4. **实盘差异**: 回测结果与实盘可能有差异

## 参考资料

- 原始策略：https://www.joinquant.com/post/15002
- RSRS指标原理：阻力支撑相对强度
- Backtrader文档：https://www.backtrader.com/docu/

---

**状态**: ✅ 策略已实现并测试
**更新时间**: 2026-05-02