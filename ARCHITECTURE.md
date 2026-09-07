# Backtrader 项目整体架构报告

> 分析日期：2026-06-22
> 项目版本：1.9.78.123

---

## 一、项目全景

本项目在开源 Backtrader 回测框架基础上，构建了一套 **本地量化回测平台（BackQuant）**，包含三个核心层次：

```
┌──────────────────────────────────────────────────────────────┐
│                    用户交互层                                │
│  ┌──────────────────┐  ┌──────────────────────────────────┐  │
│  │  Web UI (React)  │  │  Dash UI (Plotly Bootstrap)     │  │
│  │  :5173           │  │  :8050                           │  │
│  └────────┬─────────┘  └────────────┬─────────────────────┘  │
│           │                         │                        │
├───────────┼─────────────────────────┼────────────────────────┤
│           │      API 服务层         │                        │
│           │  ┌──────────────────┐   │                        │
│           └──│  Flask API       │───┘                        │
│              │  :8060           │                            │
│              └────────┬─────────┘                            │
├───────────────────────┼──────────────────────────────────────┤
│                       │  回测引擎层                          │
│  ┌────────────────────┼──────────────────────────────┐      │
│  │  Strategy Registry │  Runner │ Result Extractor   │      │
│  │  Sandbox    │ JQ Adapter │ Data Fetcher          │      │
│  └────────────────────┼──────────────────────────────┘      │
│                       │                                    │
├───────────────────────┼──────────────────────────────────────┤
│                       │  核心框架层                        │
│  ┌────────────────────┼──────────────────────────────┐      │
│  │  Backtrader Core (cerebro / strategy / feed /     │      │
│  │  indicators / analyzers / brokers)                │      │
│  └───────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────┘
```

---

## 二、目录结构总览

```
backtrader/                          # 项目根目录
├── backtrader/                      # ⚙️ 核心框架（171个Python文件）
│   ├── cerebro.py                   # 核心引擎 - 回测调度中心
│   ├── strategy.py                  # 策略基类
│   ├── feed.py / feeds/             # 数据源基类及实现
│   ├── indicator.py / indicators/   # 指标基类及122个内置指标
│   ├── analyzer.py / analyzers/     # 分析器（夏普、回撤、交易统计）
│   ├── broker.py / brokers/         # 经纪人（回测/IB/Oanda）
│   ├── linebuffer.py                # 核心数据结构 - 时间序列缓冲区
│   ├── order.py                     # 订单系统
│   ├── position.py                  # 仓位管理
│   ├── sizer.py / sizers/           # 仓位管理器
│   ├── plot/                        # matplotlib 绘图
│   ├── stores/                      # 实盘数据源（IB/Oanda/VC）
│   └── ...
│
├── strategies/                      # 📊 策略库
│   ├── etf/                         # ETF动量轮动策略
│   │   ├── etf.py                   #   聚宽格式主策略（UI默认加载）
│   │   ├── etf2.py                  #   策略变体
│   │   ├── etf_backtest.py          #   Backtrader格式适配
│   │   └── nine_hundrads.py         #   九百ETF策略
│   ├── etf_rotate/                  # ETF轮动策略集合
│   │   ├── wufu.py                  #   五福闹新春 v5.2（聚宽格式）
│   │   ├── etf_rotate.py            #   基础轮动
│   │   ├── etf_rotate_qmt.py        #   QMT实盘版
│   │   └── EFT_roteate_simple.py   #   简化版
│   ├── rsrs/                        # RSRS阻力支撑相对强度策略
│   │   ├── rsrc_strategy.py         #   基础版
│   │   ├── rsrc_strategy_full.py    #   完整版
│   │   └── rsrc_backtest*.py        #   回测脚本
│   ├── ma_following.py              # 均线跟随策略
│   ├── RSRC_value.py                # RSRS价值策略
│   └── First-board-to-second-board/ # 一板到二板打板策略
│
├── ui/                              # 🖥️ 可视化回测平台
│   ├── app.py                       # Dash应用入口 (:8050)
│   ├── api.py                       # Flask API入口 (:8060)
│   ├── assets/style.css             # 全局样式
│   ├── layouts/                     # 页面布局
│   │   ├── sidebar.py               #   左侧策略配置面板
│   │   ├── chart_tab.py             #   收益概览Tab
│   │   ├── metrics_tab.py           #   归因分析Tab
│   │   └── trades_tab.py            #   交易详情Tab
│   ├── callbacks/                   # Dash回调逻辑
│   │   ├── backtest_callbacks.py    #   回测控制
│   │   ├── strategy_callbacks.py    #   策略选择
│   │   └── upload_callbacks.py      #   策略上传
│   ├── engines/                     # 回测引擎
│   │   ├── data_fetcher.py          #   数据获取（akshare + 腾讯兜底）
│   │   ├── runner.py                #   回测执行（同步/异步）
│   │   └── result_extractor.py      #   结果提取与结构化
│   ├── strategies/                  # 策略注册
│   │   ├── registry.py              #   策略注册表（单例）
│   │   ├── sma_cross.py             #   SMA双均线内置策略
│   │   ├── etf_rotate.py            #   ETF轮动策略适配器
│   │   └── joinquant_builtin.py     #   聚宽策略自动注册
│   └── utils/                       # 工具
│       ├── sandbox.py               #   策略安全执行（AST检查+受限命名空间）
│       └── joinquant_adapter.py     #   聚宽→Backtrader适配器
│
├── web/                             # 🌐 React前端
│   ├── server.mjs                   # Node.js静态文件服务器 (:5173)
│   ├── index.html                   # SPA入口
│   ├── src/app.js                   # React应用（~2150行，零构建工具链）
│   ├── src/styles.css               # 样式
│   └── vendor/                      # 预打包依赖（React/HTM/ECharts）
│
├── main.py                          # CLI回测入口（均线跟随策略）
├── samples/                         # Backtrader官方示例（70个）
├── tests/                           # 测试用例
├── datas/                           # 示例数据（CSV）
├── doc/                             # 中文文档
├── tools/                           # 工具脚本
│   ├── bt-run.py                    #   命令行回测运行器
│   ├── yahoodownload.py             #   Yahoo数据下载
│   └── rewrite-data.py              #   数据格式转换
├── contrib/                         # 社区贡献
│   ├── datas/                       #   示例数据
│   └── samples/                     #   示例策略
└── setup.py                         # 安装配置
```

---

## 三、核心模块详解

### 3.1 回测引擎层（ui/engines/）

这是整个平台的计算核心，负责从数据获取到回测执行的完整流程：

```
用户点击"运行回测"
       │
       ▼
┌─ runner.py ──────────────────────────────────────────────┐
│  1. 并发下载数据（data_fetcher, ThreadPoolExecutor）      │
│  2. 对齐到主日历（_align_to_master_calendar）             │
│  3. 创建 Cerebro + 添加数据源 + 添加策略                 │
│  4. 添加分析器（Sharpe/DrawDown/Returns/Trade/TimeReturn）│
│  5. cerebro.run() 执行回测                               │
│  6. extract_all() 提取结构化结果                         │
└──────────────────────────────────────────────────────────┘
       │
       ▼
┌─ data_fetcher.py ────────────────────────────────────────┐
│  数据源优先级：                                          │
│  1. 内存缓存 → 磁盘缓存(.cache/market_data/)            │
│  2. akshare（东方财富源）                                │
│  3. 腾讯财经接口（兜底）                                 │
│                                                          │
│  支持：ETF / 指数 / 股票 三类数据                       │
│  缓存策略：超集复用（更宽日期范围的缓存可切片使用）       │
└──────────────────────────────────────────────────────────┘
       │
       ▼
┌─ result_extractor.py ────────────────────────────────────┐
│  提取内容：                                              │
│  • 策略净值曲线 / 基准净值曲线 / 超额收益               │
│  • 买卖信号 + 信号统计分析                              │
│  • 绩效指标（总收益/年化/夏普/回撤/胜率/盈亏比）         │
│  • 逐笔交易记录 / 持仓 / 订单流水                       │
│  • 策略日志                                              │
└──────────────────────────────────────────────────────────┘
```

**异步执行机制**：`start_backtest()` 在后台线程中运行，通过 `_results_store` 字典 + `threading.Lock` 管理状态，前端通过 `check_result(task_id)` 轮询获取进度和结果。

**实时进度**：`_RealtimeProgressAnalyzer` 在回测过程中每隔 N 根 bar 或 N 秒回调一次，推送增量净值数据，实现"边跑边画"。

### 3.2 聚宽适配器（ui/utils/joinquant_adapter.py）

这是本项目的关键创新——**将聚宽（JoinQuant）格式的策略代码无修改地在本地 Backtrader 上运行**：

```
聚宽策略源码                    Backtrader 策略类
┌──────────────────┐          ┌──────────────────────┐
│ initialize(ctx)  │          │ class JQStrategy     │
│ handle_data(ctx) │  ──→    │   __init__ → initialize│
│ run_daily(func)  │          │   next → handle_data  │
│ order()          │          │        + run_daily    │
│ attribute_history│          │        + order→bt.order│
│ get_current_data │          │        + attr_hist→... │
│ g.xxx            │          │        + g→namespace   │
└──────────────────┘          └──────────────────────┘
```

**适配映射**：

| 聚宽 API | 适配实现 |
|----------|----------|
| `order(security, amount)` | `strategy.buy()/sell()` |
| `order_target_value(security, value)` | `strategy.order_target_size()` |
| `order_target_percent(security, pct)` | 计算 value 后调 `order_target_value` |
| `attribute_history(security, count, unit, fields)` | `data.line.get(size=count)` 或快速 numpy 路径 |
| `get_current_data()` | `_CurrentDataProxy` 封装 |
| `run_daily(func, time)` | 注册到 `_jq_scheduled_funcs`，在 `next()` 中调用 |
| `context.portfolio` | `_build_portfolio()` 从 broker 状态构建 |
| `g.xxx` | 全局命名空间共享的 `SimpleNamespace` |

**证券代码映射**：聚宽用 `510300.XSHG` 格式，Backtrader 用纯数字 `510300`。适配器通过 `_normalize_security()` 和 `_suffix_for_code()` 双向转换。

### 3.3 策略安全沙箱（ui/utils/sandbox.py）

支持用户上传 `.py` 策略文件并在受限环境中执行：

```
上传 .py 文件
     │
     ▼
┌─ AST 安全检查 ──────────────────────────────────┐
│  • 禁止导入: os, subprocess, socket, requests... │
│  • 禁止调用: eval, exec, open, __import__...    │
│  • 禁止访问: __class__, __globals__, __dict__... │
│  • 检查策略入口: bt.Strategy子类 或 聚宽格式     │
└──────────────────────────────────────────────────┘
     │
     ▼
┌─ 受限命名空间执行 ──────────────────────────────┐
│  safe_builtins = {range, len, int, float, ...}  │
│  namespace = {                                   │
│    bt, np, pd, math,    # 允许的库              │
│    g,                    # 聚宽全局状态          │
│    order, order_target_value, ...  # 聚宽API桩   │
│  }                                               │
│  exec(compiled_code, namespace)                  │
└──────────────────────────────────────────────────┘
     │
     ▼
  查找 bt.Strategy 子类 → 直接使用
  或 聚宽 initialize/handle_data → create_joinquant_strategy()
```

**TA-Lib 兜底**：如果系统未安装 TA-Lib，沙箱提供 `_TalibFallback`，用纯 numpy 实现 ATR 指标。

### 3.4 策略注册表（ui/strategies/registry.py）

单例模式的策略管理器，统一管理内置策略和用户上传的自定义策略：

```python
StrategyRegistry.register(
    name='SMA双均线交叉',
    strategy_class=SMACrossStrategy,
    description='短期均线上穿长期均线买入，下穿卖出',
    category='builtin',  # 或 'custom'
)
```

**自动参数提取**：从 `bt.Strategy.params` 元组自动生成 UI 可编辑的参数 schema（类型推断 + 中文标签映射）。

**内置策略自动注册**：
1. `SMACrossStrategy` — SMA 双均线交叉
2. `ETFRotateStrategy` — ETF 动量轮动（从 `strategies/etf/etf_backtest.py` 导入）
3. `ETF轮动最终优化（聚宽）` — 从 `strategies/etf/etf.py` 读取源码，经沙箱执行 + 聚宽适配器转换

---

## 四、双前端架构

项目提供了两套前端，共享同一个 Flask API 后端：

### 4.1 Dash UI（:8050）

- **技术栈**：Dash + Plotly + Bootstrap
- **入口**：`python -m ui.app`
- **特点**：Python 全栈，回调机制，适合快速迭代
- **布局**：聚宽风格顶部导航 + 策略工具条 + 左侧配置面板 + 右侧内容区

### 4.2 React UI（:5173）

- **技术栈**：React + HTM（模板字面量）+ ECharts，零构建工具链
- **入口**：`node web/server.mjs`（静态文件服务）+ `python -m ui.api`（API服务）
- **特点**：无构建步骤，vendor 目录预打包 React/HTM/ECharts，单文件 `app.js`（~2150行）
- **功能**：
  - 策略选择 + 参数配置 + 标的选择
  - 运行回测 + 实时进度 + 增量绘制
  - 多维收益对比图（策略/基准/超额/标的/对比）
  - 回撤曲线 + 信号分析
  - 交易记录 + 订单流水
  - 策略代码编辑器（支持聚宽/Backtrader格式）
  - 策略上传（.py文件）
  - 对比标的添加
  - JSON/CSV导出

### 4.3 Flask API（:8060）

两套前端共享的 API 层：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/meta` | GET | 策略列表+ETF池+基准+默认配置 |
| `/api/backtests` | GET | 回测任务列表 |
| `/api/backtests` | POST | 创建回测任务 |
| `/api/backtests/<id>` | GET | 查询回测结果（轮询） |
| `/api/market/series` | GET/POST | 行情数据查询 |
| `/api/strategies/upload` | POST | 上传自定义策略 |
| `/api/strategies/upload-base64` | POST | Base64策略上传 |

---

## 五、策略库详解

### 5.1 策略格式双轨制

项目支持两种策略格式，通过适配器统一在 Backtrader 上运行：

| 格式 | 入口 | 适配方式 | 示例 |
|------|------|----------|------|
| **Backtrader** | `class Xxx(bt.Strategy)` | 直接使用 | `sma_cross.py`, `etf_backtest.py` |
| **聚宽** | `initialize(ctx)` + `handle_data/run_daily` | `joinquant_adapter.py` 转换 | `etf.py`, `wufu.py` |

### 5.2 策略分类

| 策略 | 类型 | 格式 | 核心逻辑 |
|------|------|------|----------|
| **SMA双均线交叉** | 趋势跟踪 | Backtrader | 短均线上穿长均线买入 |
| **ETF动量轮动** | 动量轮动 | Backtrader | 年化收益×R²得分排序 |
| **ETF轮动最终优化** | 动量轮动 | 聚宽 | 加权回归动量+走弱期切换 |
| **五福闹新春 v5.2** | 动量轮动 | 聚宽 | WLS回归动量+双市场状态+动态池 |
| **RSRS** | 阻力支撑 | Backtrader | 相对强度指标择时 |
| **均线跟随** | 趋势跟踪 | Backtrader | 均线方向跟随+止损止盈 |
| **一板到二板** | 打板 | 聚宽 | 涨停板选股 |

---

## 六、数据流架构

### 6.1 回测数据流

```
akshare / 腾讯财经
       │
       ▼
┌─ data_fetcher.py ──────────────────────────────┐
│  download_data(code, start, end, data_type)    │
│  → 内存缓存 → 磁盘缓存(.pkl) → 超集复用      │
│  → DataFrame(DatetimeIndex, OHLCV)            │
└────────────────────────────────────────────────┘
       │
       ▼  并发下载（ThreadPoolExecutor, max_workers=8）
       │
┌─ runner.py ────────────────────────────────────┐
│  _download_data_feeds() → dict[code, DataFrame]│
│  _align_to_master_calendar() → 对齐日历        │
│  PandasDataFeed(dataname=df) → bt.feeds.Pandas │
│  cerebro.adddata(feed, name=code)             │
└────────────────────────────────────────────────┘
       │
       ▼
┌─ Backtrader Cerebro ──────────────────────────┐
│  cerebro.run() → strat                        │
└────────────────────────────────────────────────┘
       │
       ▼
┌─ result_extractor.py ──────────────────────────┐
│  extract_all(strat, data_feeds) → dict        │
│  {nav, returns, benchmark, signals,           │
│   metrics, trades, positions, orders, logs}   │
└────────────────────────────────────────────────┘
       │
       ▼
  前端渲染（ECharts / Plotly）
```

### 6.2 策略上传数据流

```
用户上传 .py 文件
       │
       ▼
┌─ api.py: /api/strategies/upload ──────────────┐
│  1. 读取源码（文件或base64）                   │
│  2. validate_strategy_code() → AST安全检查     │
│  3. execute_strategy_code() → 受限命名空间执行 │
│     ├─ 找到 bt.Strategy 子类 → 直接使用       │
│     └─ 找到聚宽入口 → create_joinquant_strategy│
│  4. StrategyRegistry.register() → 注册到注册表 │
│  5. 返回更新后的策略列表                       │
└────────────────────────────────────────────────┘
```

---

## 七、核心设计模式

### 7.1 聚宽适配器模式

**问题**：聚宽策略使用 `initialize(context)` / `handle_data(context, data)` / `run_daily()` 等专有 API，无法直接在 Backtrader 上运行。

**解决方案**：`joinquant_adapter.py` 创建一个动态的 `bt.Strategy` 子类，在 `__init__` 中调用 `initialize()`，在 `next()` 中调用 `handle_data()` 和注册的 `run_daily` 函数，同时将聚宽 API 函数绑定到命名空间。

**关键价值**：聚宽社区海量策略代码可直接在本地运行，无需改写。

### 7.2 策略注册表模式

**问题**：内置策略、动态导入策略、用户上传策略需要统一管理。

**解决方案**：`StrategyRegistry` 单例，提供 `register/get/list_all/get_dropdown_options` 接口，自动从 `bt.Strategy.params` 提取参数 schema。

### 7.3 安全沙箱模式

**问题**：用户上传的策略代码可能包含危险操作（文件访问、网络请求等）。

**解决方案**：AST 级别安全检查 + 受限 `__builtins__` + 白名单库导入。本地/个人使用场景，非加密级安全。

### 7.4 异步回测模式

**问题**：回测可能耗时数分钟，需要非阻塞执行 + 实时进度反馈。

**解决方案**：`start_backtest()` 在 daemon 线程中运行，`_results_store` 字典 + `threading.Lock` 管理状态，`_RealtimeProgressAnalyzer` 在回测过程中推送增量数据，前端 900ms 轮询。

### 7.5 数据缓存模式

**问题**：频繁回测时重复下载相同数据，浪费时间和网络带宽。

**解决方案**：三级缓存：内存字典 → 磁盘 pickle → 超集复用（更宽日期范围的缓存可切片给更窄的请求使用）。

---

## 八、技术栈汇总

| 层次 | 技术 | 用途 |
|------|------|------|
| **核心框架** | Backtrader 1.9.78 | 回测引擎 |
| **数据获取** | akshare | 东方财富源行情数据 |
| **数据获取** | requests | 腾讯财经兜底 |
| **后端API** | Flask | REST API 服务 |
| **Dash前端** | Dash + Plotly + Bootstrap | Python全栈UI |
| **React前端** | React + HTM + ECharts | 零构建SPA |
| **前端服务** | Node.js (http) | 静态文件服务 |
| **策略适配** | 自研 joinquant_adapter | 聚宽→Backtrader |
| **安全执行** | ast +受限命名空间 | 策略沙箱 |
| **数据处理** | pandas + numpy | 数据处理与计算 |
| **并发** | threading + ThreadPoolExecutor | 异步回测+并发下载 |

---

## 九、启动方式

| 方式 | 命令 | 访问地址 |
|------|------|----------|
| Dash UI | `python -m ui.app` | http://127.0.0.1:8050 |
| React UI + API | `python -m ui.api` + `node web/server.mjs` | http://127.0.0.1:5173 → API :8060 |
| CLI回测 | `python main.py [--mode backtest\|optimize]` | 终端输出 |
| 策略回测 | `python strategies/etf/etf_backtest.py` | 终端输出 |

---

## 十、架构优势与不足

### ✅ 优势

1. **聚宽生态兼容**：通过适配器，聚宽社区海量策略可直接本地运行，这是最大的差异化价值
2. **双前端灵活选择**：Dash（快速迭代）和 React（现代体验）满足不同场景
3. **策略安全沙箱**：AST检查+受限命名空间，支持用户上传策略而不危及系统安全
4. **实时增量绘制**：回测过程中边跑边画，用户体验好
5. **三级数据缓存**：内存→磁盘→超集复用，大幅减少重复下载
6. **策略自动注册**：聚宽策略文件放入 `strategies/` 目录即可自动出现在UI中

### ⚠️ 不足

1. **React前端无构建工具链**：`app.js` 单文件 2150 行，无组件拆分、无类型检查、无 HMR，维护成本高
2. **聚宽适配器不完整**：部分聚宽 API 未实现（如 `get_trade_days`、`get_all_securities`、`record` 等），复杂策略可能运行失败
3. **Dash UI 与 React UI 功能不同步**：两套前端维护成本高，功能覆盖不一致
4. **无持久化存储**：回测结果仅保存在内存中（`_results_store` + `_TASK_HISTORY`），服务重启后丢失
5. **沙箱安全非加密级**：AST检查可被绕过（如通过 `__build_class__` 间接访问），仅适合本地/个人场景
6. **无参数优化UI**：Backtrader 支持 `optstrategy` 参数优化，但 UI 仅支持单次回测
7. **无实盘对接**：虽然 Backtrader 支持 IB/Oanda 实盘，但 UI 层未集成

---

*报告生成时间：2026-06-22*
