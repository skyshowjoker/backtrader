const React = window.React;
const ReactDOM = window.ReactDOM;
const htm = window.htm;
const echarts = window.echarts;

if (!React || !ReactDOM || !htm || !echarts) {
  throw new Error('前端依赖未加载，请确认 /vendor 下的 React、HTM、ECharts 文件可访问。');
}

const {useEffect, useMemo, useRef, useState} = React;
const {createRoot} = ReactDOM;
const html = htm.bind(React.createElement);
const API_BASE = window.__BACKTRADER_API__ || 'http://127.0.0.1:8060/api';

const DEFAULT_TOGGLES = [
  'strategy_return',
  'benchmark_return',
  'excess_return',
  'compare_return',
  'signals',
];

const curveOptions = [
  ['strategy_nav', '策略净值'],
  ['strategy_return', '策略收益'],
  ['benchmark_return', '基准收益'],
  ['excess_return', '超额收益'],
  ['compare_return', '对比标的'],
  ['underlying_price', '标的价格'],
  ['underlying_return', '标的收益'],
  ['signals', '买卖信号'],
];

const chartRangeOptions = [
  ['1m', '1月'],
  ['3m', '3月'],
  ['6m', '6月'],
  ['ytd', 'YTD'],
  ['all', '全部'],
];

const palette = {
  blue: '#3564a8',
  green: '#16a085',
  gold: '#d59b43',
  red: '#d9594c',
  slate: '#6d7d93',
  violet: '#7764c8',
  cyan: '#2596a6',
};

function App() {
  const [meta, setMeta] = useState({strategies: [], etfs: [], benchmarks: [], defaults: {}});
  const [workspaceMode, setWorkspaceMode] = useState('detail');
  const [activeTab, setActiveTab] = useState('overview');
  const [strategyName, setStrategyName] = useState('');
  const [params, setParams] = useState({});
  const [dataCodes, setDataCodes] = useState(['510300']);
  const [benchmark, setBenchmark] = useState('000300');
  const [startDate, setStartDate] = useState('2020-01-01');
  const [endDate, setEndDate] = useState('2025-12-31');
  const [initialCash, setInitialCash] = useState('1000000');
  const [commission, setCommission] = useState('0.0002');
  const [frequency, setFrequency] = useState('daily');
  const [toggles, setToggles] = useState(DEFAULT_TOGGLES);
  const [result, setResult] = useState({});
  const [taskId, setTaskId] = useState('');
  const [runStatus, setRunStatus] = useState({type: 'idle', text: '就绪'});
  const [compareInput, setCompareInput] = useState('');
  const [compareSeries, setCompareSeries] = useState([]);
  const [compareLoading, setCompareLoading] = useState(false);
  const [chartRange, setChartRange] = useState('all');
  const [strategyFormat, setStrategyFormat] = useState('auto');
  const [strategySource, setStrategySource] = useState('');
  const [sourceFilename, setSourceFilename] = useState('custom_strategy.py');
  const [taskHistory, setTaskHistory] = useState([]);
  const [activityLog, setActivityLog] = useState(['系统就绪']);
  const [runStartedAt, setRunStartedAt] = useState(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [runProgress, setRunProgress] = useState({stage: 'idle'});

  useEffect(() => {
    loadMeta().then((payload) => {
      setMeta(payload);
      setStrategyName(payload.defaults.strategy || payload.strategies[0]?.name || '');
      setDataCodes(payload.defaults.data_codes || ['510300']);
      setBenchmark(payload.defaults.benchmark || '000300');
      setStartDate(payload.defaults.start_date || '2020-01-01');
      setEndDate(payload.defaults.end_date || '2025-12-31');
      setInitialCash(payload.defaults.initial_cash || '1000000');
      setCommission(payload.defaults.commission || '0.0002');
      setFrequency(payload.defaults.frequency || 'daily');
      setStrategySource(payload.templates?.joinquant || '');
      refreshTasks();
    }).catch((error) => {
      setRunStatus({type: 'error', text: error.message});
      appendLog(`初始化失败: ${error.message}`);
    });
  }, []);

  const selectedStrategy = useMemo(() => {
    return meta.strategies.find((item) => item.name === strategyName);
  }, [meta.strategies, strategyName]);

  useEffect(() => {
    if (!selectedStrategy) {
      return;
    }
    const next = {};
    for (const param of selectedStrategy.params || []) {
      next[param.name] = param.default;
    }
    setParams(next);
    if (selectedStrategy.preferred_data_codes?.length) {
      setDataCodes(selectedStrategy.preferred_data_codes);
    }
  }, [selectedStrategy?.name]);

  useEffect(() => {
    if (!taskId) {
      return undefined;
    }

    let stopped = false;
    let pollCount = 0;
    async function tick() {
      try {
        const payload = await fetchJson(`${API_BASE}/backtests/${taskId}`);
        if (stopped) {
          return;
        }
        pollCount += 1;
        const progress = payload.progress || payload.data?.progress || {};
        setRunProgress(progress);
        if (Number.isFinite(Number(progress.elapsed_seconds))) {
          setElapsedSeconds(Number(progress.elapsed_seconds));
        }
        if (payload.data) {
          setResult((current) => mergeBacktestResult(current, payload.data));
        }
        if (pollCount % 4 === 0) {
          refreshTasks();
        }
        if (payload.status === 'done') {
          setRunStatus({type: 'success', text: '回测完成'});
          appendLog(`任务 ${taskId} 回测完成`);
          setRunStartedAt(null);
          setTaskId('');
          refreshTasks();
          return;
        }
        if (payload.status === 'error') {
          setRunStatus({type: 'error', text: payload.data || '回测失败'});
          appendLog(`任务 ${taskId} 失败: ${payload.data || '回测失败'}`);
          setRunStartedAt(null);
          setTaskId('');
          refreshTasks();
          return;
        }
        setRunStatus({type: 'running', text: payload.message || '回测运行中'});
        window.setTimeout(tick, 900);
      } catch (error) {
        if (!stopped) {
          setRunStatus({type: 'error', text: error.message});
          setRunStartedAt(null);
          setTaskId('');
        }
      }
    }
    tick();

    return () => {
      stopped = true;
    };
  }, [taskId]);

  useEffect(() => {
    if (!taskId || !runStartedAt) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      setElapsedSeconds((Date.now() - runStartedAt) / 1000);
    }, 250);
    return () => window.clearInterval(timer);
  }, [taskId, runStartedAt]);

  async function runBacktest() {
    if (!strategyName) {
      setRunStatus({type: 'error', text: '请选择策略'});
      return;
    }
    const selectedCodes = [...new Set(dataCodes)];
    if (!selectedCodes.length) {
      setRunStatus({type: 'error', text: '请至少选择一个标的'});
      return;
    }
    const validationError = validateRunConfig({startDate, endDate, initialCash, commission});
    if (validationError) {
      setRunStatus({type: 'error', text: validationError});
      appendLog(`参数校验失败: ${validationError}`);
      return;
    }

    setRunStatus({type: 'running', text: '准备启动回测'});
    setResult({});
    setRunProgress({stage: 'queued'});
    setElapsedSeconds(0);
    setRunStartedAt(Date.now());
    setWorkspaceMode('detail');
    appendLog(`启动回测: ${strategyName} / ${selectedCodes.join(', ')}`);
    try {
      const payload = await fetchJson(`${API_BASE}/backtests`, {
        method: 'POST',
        body: JSON.stringify({
          strategy: strategyName,
          params: coerceParams(selectedStrategy?.params || [], params),
          start_date: startDate,
          end_date: endDate,
          initial_cash: initialCash,
          commission,
          benchmark,
          data_codes: selectedCodes,
          frequency,
          data_type: 'etf',
        }),
      });
      setTaskId(payload.task_id);
      setRunStatus({type: 'running', text: '行情加载中'});
      appendLog(`任务 ${payload.task_id} 已创建`);
      refreshTasks();
    } catch (error) {
      setRunStatus({type: 'error', text: error.message});
      setRunStartedAt(null);
      appendLog(`启动失败: ${error.message}`);
    }
  }

  async function uploadStrategy(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    const body = new FormData();
    body.append('file', file);
    body.append('strategy_format', strategyFormat);
    setRunStatus({type: 'running', text: '策略上传中'});

    try {
      const payload = await fetchJson(`${API_BASE}/strategies/upload`, {
        method: 'POST',
        body,
      });
      setMeta((current) => ({...current, strategies: payload.strategies}));
      setStrategyName(payload.strategy);
      setRunStatus({type: 'success', text: `策略已添加: ${payload.strategy}`});
      appendLog(`上传策略成功: ${payload.strategy}`);
    } catch (error) {
      setRunStatus({type: 'error', text: error.message});
      appendLog(`上传策略失败: ${error.message}`);
    } finally {
      event.target.value = '';
    }
  }

  async function saveSourceStrategy() {
    if (!strategySource.trim()) {
      setRunStatus({type: 'error', text: '策略源码为空'});
      return;
    }

    const body = new FormData();
    body.append('source_code', strategySource);
    body.append('filename', sourceFilename || 'custom_strategy.py');
    body.append('strategy_format', strategyFormat);
    setRunStatus({type: 'running', text: '正在注册策略'});

    try {
      const payload = await fetchJson(`${API_BASE}/strategies/upload`, {
        method: 'POST',
        body,
      });
      setMeta((current) => ({...current, strategies: payload.strategies}));
      setStrategyName(payload.strategy);
      setRunStatus({type: 'success', text: `策略已注册: ${payload.strategy}`});
      appendLog(`源码策略已注册: ${payload.strategy}`);
    } catch (error) {
      setRunStatus({type: 'error', text: error.message});
      appendLog(`源码注册失败: ${error.message}`);
    }
  }

  function loadTemplate(format = strategyFormat) {
    const key = format === 'backtrader' ? 'backtrader' : 'joinquant';
    setStrategyFormat(format === 'auto' ? 'joinquant' : format);
    setStrategySource(meta.templates?.[key] || '');
    setSourceFilename(key === 'backtrader' ? 'custom_backtrader.py' : 'custom_joinquant.py');
  }

  async function refreshTasks() {
    try {
      const payload = await fetchJson(`${API_BASE}/backtests`);
      setTaskHistory(payload.tasks || []);
    } catch (error) {
      appendLog(`任务列表刷新失败: ${error.message}`);
    }
  }

  async function openTask(taskIdToOpen) {
    try {
      const payload = await fetchJson(`${API_BASE}/backtests/${taskIdToOpen}`);
      if (payload.data && typeof payload.data === 'object') {
        setResult(payload.data);
        setWorkspaceMode('detail');
        setActiveTab('overview');
        setRunStatus({type: 'success', text: `已载入任务 ${taskIdToOpen}`});
      } else if (payload.status === 'error') {
        setRunStatus({type: 'error', text: payload.data || '任务失败'});
      } else {
        setRunStatus({type: 'running', text: payload.message || '任务运行中'});
      }
      refreshTasks();
    } catch (error) {
      setRunStatus({type: 'error', text: error.message});
    }
  }

  async function addCompareSeries() {
    const codes = parseSymbolInput(compareInput);
    if (!codes.length) {
      setRunStatus({type: 'error', text: '请输入对比标的代码'});
      return;
    }

    setCompareLoading(true);
    setRunStatus({type: 'running', text: '加载对比曲线'});
    try {
      const query = new URLSearchParams({
        codes: codes.join(','),
        start_date: startDate,
        end_date: endDate,
        data_type: 'auto',
      });
      const payload = await fetchJson(`${API_BASE}/market/series?${query.toString()}`);
      if (payload.series?.length) {
        setCompareSeries((current) => mergeSeries(current, payload.series));
        setToggles((current) => current.includes('compare_return') ? current : [...current, 'compare_return']);
        setCompareInput('');
        setRunStatus({type: 'success', text: `已添加对比曲线: ${payload.series.map((item) => item.code).join(', ')}`});
        appendLog(`添加对比曲线: ${payload.series.map((item) => `${item.code} ${item.name}`).join(' / ')}`);
      } else {
        setRunStatus({type: 'error', text: '未获取到对比行情'});
      }

      if (payload.errors?.length) {
        appendLog(`对比曲线部分失败: ${payload.errors.map((item) => `${item.code} ${item.message}`).join('；')}`);
      }
    } catch (error) {
      setRunStatus({type: 'error', text: error.message});
      appendLog(`对比曲线加载失败: ${error.message}`);
    } finally {
      setCompareLoading(false);
    }
  }

  function removeCompareSeries(code) {
    setCompareSeries((current) => current.filter((item) => item.code !== code));
    appendLog(`移除对比曲线: ${code}`);
  }

  function clearCompareSeries() {
    setCompareSeries([]);
    appendLog('已清空对比曲线');
  }

  function exportBacktestJson() {
    if (!hasResultData(result)) {
      setRunStatus({type: 'error', text: '暂无可导出结果'});
      return;
    }
    downloadText(
      `backtest-${new Date().toISOString().slice(0, 10)}.json`,
      JSON.stringify(result, null, 2),
      'application/json',
    );
    appendLog('已导出回测JSON');
  }

  function exportTradesCsv() {
    const trades = [
      ...(result.positions || []).map((item) => ({...item, status: 'open'})),
      ...(result.trades || []).map((item) => ({...item, status: item.status || 'closed'})),
    ];
    if (!trades.length) {
      setRunStatus({type: 'error', text: '暂无交易记录'});
      return;
    }
    downloadText('trades.csv', toCsv(trades, [
      'status', 'data_name', 'direction', 'entry_date', 'exit_date', 'entry_price', 'exit_price', 'last_price', 'size', 'gross_pnl', 'net_pnl', 'duration',
    ]), 'text/csv;charset=utf-8');
    appendLog('已导出交易CSV');
  }

  function exportSignalsCsv() {
    const signals = result.signals || [];
    if (!signals.length) {
      setRunStatus({type: 'error', text: '暂无策略信号'});
      return;
    }
    downloadText('signals.csv', toCsv(signals, ['date', 'type', 'data_name', 'price', 'size']), 'text/csv;charset=utf-8');
    appendLog('已导出信号CSV');
  }

  function appendLog(message) {
    const time = new Date().toLocaleTimeString('zh-CN', {hour12: false});
    setActivityLog((current) => [`${time}  ${message}`, ...current].slice(0, 80));
  }

  return html`
    <div className="shell">
      <${TopNav} />
      <${StrategyBar} mode=${workspaceMode} setMode=${setWorkspaceMode} />
      <${RunToolbar}
        startDate=${startDate}
        setStartDate=${setStartDate}
        endDate=${endDate}
        setEndDate=${setEndDate}
        initialCash=${initialCash}
        setInitialCash=${setInitialCash}
        commission=${commission}
        setCommission=${setCommission}
        benchmark=${benchmark}
        setBenchmark=${setBenchmark}
        benchmarks=${meta.benchmarks}
        frequency=${frequency}
        setFrequency=${setFrequency}
        runStatus=${runStatus}
        isRunning=${Boolean(taskId)}
        elapsedSeconds=${elapsedSeconds}
        runProgress=${runProgress}
        onRun=${runBacktest}
      />
      <main className="workspace">
        <${Sidebar}
          strategies=${meta.strategies}
          selectedStrategy=${selectedStrategy}
          strategyName=${strategyName}
          setStrategyName=${setStrategyName}
          params=${params}
          setParams=${setParams}
          etfs=${meta.etfs}
          dataCodes=${dataCodes}
          setDataCodes=${setDataCodes}
          strategyFormat=${strategyFormat}
          setStrategyFormat=${setStrategyFormat}
          uploadStrategy=${uploadStrategy}
        />
        <section className="content-panel">
          ${workspaceMode === 'edit' && html`
            <${EditorPanel}
              strategyFormat=${strategyFormat}
              setStrategyFormat=${setStrategyFormat}
              strategySource=${strategySource}
              setStrategySource=${setStrategySource}
              sourceFilename=${sourceFilename}
              setSourceFilename=${setSourceFilename}
              loadTemplate=${loadTemplate}
              saveSourceStrategy=${saveSourceStrategy}
              selectedStrategy=${selectedStrategy}
            />
          `}
          ${workspaceMode === 'detail' && html`
            <${BacktestDetail}
              activeTab=${activeTab}
              setActiveTab=${setActiveTab}
              result=${result}
              toggles=${toggles}
              setToggles=${setToggles}
              compareInput=${compareInput}
              setCompareInput=${setCompareInput}
              compareSeries=${compareSeries}
              compareLoading=${compareLoading}
              addCompareSeries=${addCompareSeries}
              removeCompareSeries=${removeCompareSeries}
              clearCompareSeries=${clearCompareSeries}
              chartRange=${chartRange}
              setChartRange=${setChartRange}
              runStatus=${runStatus}
              isRunning=${Boolean(taskId)}
              exportBacktestJson=${exportBacktestJson}
              exportTradesCsv=${exportTradesCsv}
              exportSignalsCsv=${exportSignalsCsv}
              activityLog=${activityLog}
            />
          `}
          ${workspaceMode === 'runs' && html`
            <${RunListPanel}
              tasks=${taskHistory}
              activityLog=${activityLog}
              refreshTasks=${refreshTasks}
              openTask=${openTask}
            />
          `}
          ${workspaceMode === 'history' && html`
            <${BacktestListPanel}
              tasks=${taskHistory}
              refreshTasks=${refreshTasks}
              openTask=${openTask}
            />
          `}
        </section>
      </main>
    </div>
  `;
}

function TopNav() {
  return html`
    <header className="top-nav">
      <div className="brand">
        <span className="brand-bars"></span>
        <span className="brand-text">BackQuant</span>
      </div>
      <nav className="nav-links">
        <span>首页</span>
        <span className="active">量化研究平台</span>
        <span>策略社区</span>
        <span>帮助</span>
        <span>本地数据</span>
      </nav>
      <div className="avatar">BT</div>
    </header>
  `;
}

function StrategyBar({mode, setMode}) {
  const tabs = [
    ['edit', '编辑策略'],
    ['detail', '回测详情'],
    ['runs', '编译运行列表'],
    ['history', '回测列表'],
  ];

  return html`
    <section className="strategy-bar">
      <div className="strategy-title">
        <span className="back-mark">‹</span>
        <h1>ETF轮动最终优化</h1>
        <span className="edit-mark">✎</span>
      </div>
      <div className="workspace-tabs">
        ${tabs.map(([value, label]) => html`
          <button
            key=${value}
            type="button"
            className=${mode === value ? 'selected' : ''}
            onClick=${() => setMode(value)}
          >${label}</button>
        `)}
      </div>
    </section>
  `;
}

function RunToolbar(props) {
  const progressText = progressLabel(props.runProgress);
  return html`
    <section className="run-toolbar">
      <div className="run-settings">
        <span className="label">设置：</span>
        <input className="date-field" type="date" value=${props.startDate}
          onInput=${(event) => props.setStartDate(event.target.value)} />
        <span className="date-arrow">至</span>
        <input className="date-field" type="date" value=${props.endDate}
          onInput=${(event) => props.setEndDate(event.target.value)} />
        <span className="currency">¥</span>
        <input className="money-field" value=${props.initialCash}
          onInput=${(event) => props.setInitialCash(event.target.value)}
          inputMode="decimal" />
        <input className="commission-field" value=${props.commission}
          onInput=${(event) => props.setCommission(event.target.value)}
          inputMode="decimal" />
        <select value=${props.benchmark}
          onInput=${(event) => props.setBenchmark(event.target.value)}>
          ${props.benchmarks.map((item) => html`
            <option key=${item.code} value=${item.code}>${item.label}</option>
          `)}
        </select>
        <select value=${props.frequency}
          onInput=${(event) => props.setFrequency(event.target.value)}>
          <option value="daily">每天</option>
          <option value="weekly">每周</option>
          <option value="monthly">每月</option>
        </select>
        <span className="python-badge">Python3</span>
      </div>
      <div className="run-actions">
        <div className="run-runtime">
          <span className=${`status ${props.runStatus.type}`}>${props.runStatus.text}</span>
          <b>${runtimeText(props.isRunning, props.elapsedSeconds)}</b>
          ${progressText ? html`<em>${progressText}</em>` : null}
        </div>
        <button className="primary-action" disabled=${props.isRunning} onClick=${props.onRun}>
          ${props.isRunning ? '运行中' : '运行回测'}
        </button>
      </div>
    </section>
  `;
}

function Sidebar(props) {
  return html`
    <aside className="side-panel">
      <div className="side-form">
        <h2>策略配置</h2>
        <label>策略选择</label>
        <select value=${props.strategyName}
          onInput=${(event) => props.setStrategyName(event.target.value)}>
          ${props.strategies.map((item) => html`
            <option key=${item.name} value=${item.name}>
              ${item.category === 'custom' ? '自定义 · ' : ''}${item.name}
            </option>
          `)}
        </select>

        <label>参数配置</label>
        <${ParamEditor}
          schema=${props.selectedStrategy?.params || []}
          params=${props.params}
          setParams=${props.setParams}
        />

        <label>标的代码</label>
        <${SymbolPicker}
          etfs=${props.etfs}
          selected=${props.dataCodes}
          setSelected=${props.setDataCodes}
        />

        <label>上传自定义策略</label>
        <div className="segment">
          ${[
            ['auto', '自动'],
            ['backtrader', 'BT'],
            ['joinquant', '聚宽'],
          ].map(([value, label]) => html`
            <button
              key=${value}
              type="button"
              className=${props.strategyFormat === value ? 'selected' : ''}
              onClick=${() => props.setStrategyFormat(value)}
            >${label}</button>
          `)}
        </div>
        <label className="upload-box">
          <input type="file" accept=".py" onChange=${props.uploadStrategy} />
          <span>点击上传 .py 文件</span>
        </label>
      </div>
    </aside>
  `;
}

function ParamEditor({schema, params, setParams}) {
  if (!schema.length) {
    return html`<div className="empty-line">无可配置参数</div>`;
  }

  function update(name, value) {
    setParams((current) => ({...current, [name]: value}));
  }

  return html`
    <div className="param-list">
      ${schema.map((param) => {
        if (param.type === 'bool') {
          return html`
            <label className="check-row" key=${param.name}>
              <input
                type="checkbox"
                checked=${Boolean(params[param.name])}
                onChange=${(event) => update(param.name, event.target.checked)}
              />
              <span>${param.label}</span>
            </label>
          `;
        }
        return html`
          <div className="param-row" key=${param.name}>
            <span>${param.label}</span>
            <input
              value=${params[param.name] ?? ''}
              inputMode=${param.type === 'str' ? 'text' : 'decimal'}
              onInput=${(event) => update(param.name, event.target.value)}
            />
          </div>
        `;
      })}
    </div>
  `;
}

function SymbolPicker({etfs, selected, setSelected}) {
  function toggle(code) {
    setSelected((current) => {
      if (current.includes(code)) {
        return current.filter((item) => item !== code);
      }
      return [...current, code];
    });
  }

  return html`
    <div className="symbol-picker">
      <div className="symbol-toolbar">
        <span>${selected.length}/${etfs.length}</span>
        <div className="symbol-actions">
          <button type="button" onClick=${() => setSelected(etfs.map((item) => item.code))}>全选</button>
          <button type="button" onClick=${() => setSelected([])}>清空</button>
        </div>
      </div>
      <div className="symbol-grid">
        ${etfs.map((item) => html`
          <button
            key=${item.code}
            type="button"
            className=${selected.includes(item.code) ? 'symbol selected' : 'symbol'}
            onClick=${() => toggle(item.code)}
          >
            <span>${item.code}</span>
            <b>${item.name}</b>
          </button>
        `)}
      </div>
    </div>
  `;
}

function EditorPanel(props) {
  return html`
    <div className="single-panel editor-panel">
      <div className="panel-heading-row">
        <div>
          <h2>策略代码</h2>
          <p>支持 Backtrader 策略类，也支持聚宽 initialize / handle_data 格式。</p>
        </div>
        <div className="editor-actions">
          <button type="button" onClick=${() => props.loadTemplate('joinquant')}>聚宽模板</button>
          <button type="button" onClick=${() => props.loadTemplate('backtrader')}>BT模板</button>
          <button className="primary-mini" type="button" onClick=${props.saveSourceStrategy}>注册策略</button>
        </div>
      </div>

      <div className="editor-meta-grid">
        <label>
          文件名
          <input
            value=${props.sourceFilename}
            onInput=${(event) => props.setSourceFilename(event.target.value)}
          />
        </label>
        <label>
          策略格式
          <select
            value=${props.strategyFormat}
            onInput=${(event) => props.setStrategyFormat(event.target.value)}
          >
            <option value="auto">自动识别</option>
            <option value="backtrader">Backtrader</option>
            <option value="joinquant">聚宽</option>
          </select>
        </label>
        <div className="selected-strategy-card">
          <span>当前策略</span>
          <b>${props.selectedStrategy?.name || '--'}</b>
          <small>${props.selectedStrategy?.description || '注册后可用于顶部运行回测'}</small>
        </div>
      </div>

      <textarea
        className="code-editor"
        spellCheck="false"
        value=${props.strategySource}
        onInput=${(event) => props.setStrategySource(event.target.value)}
      />
    </div>
  `;
}

function BacktestDetail({
  activeTab,
  setActiveTab,
  result,
  toggles,
  setToggles,
  compareInput,
  setCompareInput,
  compareSeries,
  compareLoading,
  addCompareSeries,
  removeCompareSeries,
  clearCompareSeries,
  chartRange,
  setChartRange,
  runStatus,
  isRunning,
  exportBacktestJson,
  exportTradesCsv,
  exportSignalsCsv,
  activityLog,
}) {
  return html`
    <${MainTabs} activeTab=${activeTab} setActiveTab=${setActiveTab} />
    ${activeTab === 'overview' && html`
      <${OverviewPanel}
        result=${result}
        toggles=${toggles}
        setToggles=${setToggles}
        compareInput=${compareInput}
        setCompareInput=${setCompareInput}
        compareSeries=${compareSeries}
        compareLoading=${compareLoading}
        addCompareSeries=${addCompareSeries}
        removeCompareSeries=${removeCompareSeries}
        clearCompareSeries=${clearCompareSeries}
        chartRange=${chartRange}
        setChartRange=${setChartRange}
        runStatus=${runStatus}
        isRunning=${isRunning}
        exportBacktestJson=${exportBacktestJson}
        exportTradesCsv=${exportTradesCsv}
        exportSignalsCsv=${exportSignalsCsv}
      />
    `}
    ${activeTab === 'metrics' && html`<${MetricsPanel} result=${result} />`}
    ${activeTab === 'trades' && html`<${TradesPanel} result=${result} />`}
    ${activeTab === 'logs' && html`<${LogsPanel} logs=${result.logs || []} activityLog=${activityLog || []} />`}
  `;
}

function RunListPanel({tasks, activityLog, refreshTasks, openTask}) {
  const running = tasks.filter((task) => task.status === 'running');

  return html`
    <div className="single-panel">
      <div className="panel-heading-row">
        <div>
          <h2>编译运行列表</h2>
          <p>查看当前回测任务状态、运行消息和系统日志。</p>
        </div>
        <button type="button" className="secondary-action" onClick=${refreshTasks}>刷新</button>
      </div>

      <div className="run-summary-grid">
        <div><span>运行中</span><b>${running.length}</b></div>
        <div><span>总任务</span><b>${tasks.length}</b></div>
        <div><span>最近任务</span><b>${tasks[0]?.task_id || '--'}</b></div>
      </div>

      <${TaskTable} tasks=${tasks} openTask=${openTask} compact=${true} />

      <div className="log-panel">
        <h3>日志输出</h3>
        <pre>${activityLog.join('\n')}</pre>
      </div>
    </div>
  `;
}

function BacktestListPanel({tasks, refreshTasks, openTask}) {
  return html`
    <div className="single-panel">
      <div className="panel-heading-row">
        <div>
          <h2>回测列表</h2>
          <p>保存本次服务生命周期内的最近回测，可点击已完成任务载入曲线。</p>
        </div>
        <button type="button" className="secondary-action" onClick=${refreshTasks}>刷新</button>
      </div>
      <${TaskCards} tasks=${tasks} openTask=${openTask} />
      <${TaskTable} tasks=${tasks} openTask=${openTask} compact=${false} />
    </div>
  `;
}

function TaskCards({tasks, openTask}) {
  const completed = tasks.filter((task) => task.status === 'done').slice(0, 4);
  if (!completed.length) {
    return html`<div className="empty-block">暂无已完成回测。运行一次回测后，这里会展示收益、回撤和信号摘要。</div>`;
  }

  return html`
    <div className="task-card-grid">
      ${completed.map((task) => html`
        <button key=${task.task_id} type="button" className="task-card" onClick=${() => openTask(task.task_id)}>
          <span>${task.strategy}</span>
          <b>${pct(task.summary?.total_return)}</b>
          <small>${task.config?.start_date} 至 ${task.config?.end_date}</small>
          <em>信号 ${task.summary?.signals || 0} / 交易 ${task.summary?.trades || 0}</em>
        </button>
      `)}
    </div>
  `;
}

function TaskTable({tasks, openTask, compact}) {
  return html`
    <div className="trade-table-wrap task-table-wrap">
      <table className="trade-table">
        <thead>
          <tr>
            ${['任务ID', '状态', '策略', '标的', '区间', '收益', '回撤', '更新时间', '操作'].map((label) => html`
              <th key=${label}>${label}</th>
            `)}
          </tr>
        </thead>
        <tbody>
          ${tasks.length ? tasks.map((task) => html`
            <tr key=${task.task_id}>
              <td>${task.task_id}</td>
              <td><span className=${`task-status ${task.status}`}>${taskStatus(task.status)}</span></td>
              <td>${task.strategy}</td>
              <td>${(task.config?.data_codes || []).join(', ')}</td>
              <td>${task.config?.start_date || '--'} 至 ${task.config?.end_date || '--'}</td>
              <td className=${Number(task.summary?.total_return || 0) >= 0 ? 'positive' : 'negative'}>
                ${pct(task.summary?.total_return)}
              </td>
              <td>${pct(task.summary?.max_drawdown)}</td>
              <td>${task.updated_at || task.created_at || '--'}</td>
              <td>
                <button
                  type="button"
                  className="table-action"
                  disabled=${task.status !== 'done' && task.status !== 'error'}
                  onClick=${() => openTask(task.task_id)}
                >${task.status === 'done' ? '载入' : '查看'}</button>
              </td>
            </tr>
          `) : html`
            <tr><td colSpan="9" className="empty-cell">${compact ? '暂无运行任务' : '暂无回测记录'}</td></tr>
          `}
        </tbody>
      </table>
    </div>
  `;
}

function MainTabs({activeTab, setActiveTab}) {
  const tabs = [
    ['overview', '收益概览'],
    ['metrics', '归因分析'],
    ['trades', '交易详情'],
    ['logs', '日志输出'],
  ];

  return html`
    <div className="main-tabs">
      ${tabs.map(([value, label]) => html`
        <button
          key=${value}
          type="button"
          className=${activeTab === value ? 'active' : ''}
          onClick=${() => setActiveTab(value)}
        >${label}</button>
      `)}
    </div>
  `;
}

function OverviewPanel({
  result,
  toggles,
  setToggles,
  compareInput,
  setCompareInput,
  compareSeries,
  compareLoading,
  addCompareSeries,
  removeCompareSeries,
  clearCompareSeries,
  chartRange,
  setChartRange,
  runStatus,
  isRunning,
  exportBacktestJson,
  exportTradesCsv,
  exportSignalsCsv,
}) {
  const canExport = hasResultData(result);

  return html`
    <div className="panel-body">
      <${OverviewKpis} result=${result} isRunning=${isRunning} runStatus=${runStatus} />
      <div className="overview-header">
        <div>
          <h2>多维收益对比</h2>
        </div>
        <div className="curve-controls">
          ${curveOptions.map(([value, label]) => html`
            <label key=${value} className=${toggles.includes(value) ? 'curve-chip active' : 'curve-chip'}>
              <input
                type="checkbox"
                checked=${toggles.includes(value)}
                onChange=${() => setToggles((current) => toggleValue(current, value))}
              />
              <span>${label}</span>
            </label>
          `)}
        </div>
      </div>
      <div className="compare-row">
        <div className="compare-form">
          <input
            value=${compareInput}
            placeholder="510300, 159915"
            onInput=${(event) => setCompareInput(event.target.value)}
            onKeyDown=${(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                addCompareSeries();
              }
            }}
          />
          <button type="button" disabled=${compareLoading} onClick=${addCompareSeries}>
            ${compareLoading ? '加载中' : '添加对比'}
          </button>
        </div>
        <div className="compare-tags">
          ${(compareSeries || []).map((item) => html`
            <button
              key=${item.code}
              type="button"
              className="compare-tag"
              onClick=${() => removeCompareSeries(item.code)}
              title="移除"
            >
              <span>${item.name || item.code}</span>
              <b>${item.code}</b>
              <i>×</i>
            </button>
          `)}
          ${(compareSeries || []).length ? html`
            <button type="button" className="compare-clear" onClick=${clearCompareSeries}>清空对比</button>
          ` : null}
        </div>
      </div>
      <div className="chart-action-row">
        <div className="range-tabs">
          ${chartRangeOptions.map(([value, label]) => html`
            <button
              key=${value}
              type="button"
              className=${chartRange === value ? 'active' : ''}
              onClick=${() => setChartRange(value)}
            >${label}</button>
          `)}
        </div>
        <div className="export-actions">
          <button type="button" disabled=${!canExport} onClick=${exportBacktestJson}>结果JSON</button>
          <button type="button" disabled=${!canExport} onClick=${exportTradesCsv}>交易CSV</button>
          <button type="button" disabled=${!canExport} onClick=${exportSignalsCsv}>信号CSV</button>
        </div>
      </div>
      <${ReturnChart} result=${result} toggles=${toggles} compareSeries=${compareSeries} chartRange=${chartRange} />
      <div className="signal-section">
        <div className="overview-header compact">
          <h2>策略信号分析</h2>
        </div>
        <${SignalSummary} analysis=${result.signal_analysis || {}} />
        <${SignalChart} analysis=${result.signal_analysis || {}} />
      </div>
    </div>
  `;
}

function OverviewKpis({result, isRunning, runStatus}) {
  const metrics = result.metrics || {};
  const kpis = [
    ['策略收益', pct(metrics.total_return), metrics.total_return],
    ['年化收益', pct(metrics.annual_return), metrics.annual_return],
    ['超额收益', pct(last(result.excess_return_values)), last(result.excess_return_values)],
    ['最大回撤', pct(metrics.max_drawdown), -Math.abs(Number(metrics.max_drawdown || 0))],
    ['夏普比率', fixed(metrics.sharpe_ratio, 2), metrics.sharpe_ratio],
    ['交易次数', intValue(metrics.total_trades), metrics.total_trades],
  ];

  return html`
    <div className="overview-kpis">
      ${kpis.map(([label, value, raw]) => html`
        <div className="overview-kpi" key=${label}>
          <span>${label}</span>
          <b className=${metricTone(label, raw)}>${value}</b>
        </div>
      `)}
      <div className=${`overview-run-state ${isRunning ? 'running' : runStatus.type}`}>
        <span>状态</span>
        <b>${runStatus.text || '就绪'}</b>
      </div>
    </div>
  `;
}

function ReturnChart({result, toggles, compareSeries, chartRange}) {
  const ref = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!ref.current) {
      return undefined;
    }
    chartRef.current = echarts.init(ref.current, null, {renderer: 'canvas'});
    const resize = () => chartRef.current?.resize();
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current) {
      return;
    }
    chartRef.current.setOption(
      buildReturnOption(result || {}, toggles || [], compareSeries || [], chartRange),
      {notMerge: true, lazyUpdate: true},
    );
  }, [result, toggles, compareSeries, chartRange]);

  return html`<div className="chart-canvas" ref=${ref}></div>`;
}

function SignalChart({analysis}) {
  const ref = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!ref.current) {
      return undefined;
    }
    chartRef.current = echarts.init(ref.current, null, {renderer: 'canvas'});
    const resize = () => chartRef.current?.resize();
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current) {
      return;
    }
    chartRef.current.setOption(buildSignalOption(analysis || {}), {notMerge: true, lazyUpdate: true});
  }, [analysis]);

  return html`<div className="signal-canvas" ref=${ref}></div>`;
}

function SignalSummary({analysis}) {
  const symbols = analysis.symbols || [];
  const activeSymbols = symbols.filter((item) => item.buy || item.sell).length;
  const items = [
    ['全部信号', analysis.total || 0, palette.blue],
    ['买入', analysis.buy || 0, palette.green],
    ['卖出', analysis.sell || 0, palette.red],
    ['覆盖标的', activeSymbols, palette.gold],
  ];

  return html`
    <div className="signal-cards">
      ${items.map(([label, value, color]) => html`
        <div className="signal-card" key=${label}>
          <span>${label}</span>
          <b style=${{color}}>${value}</b>
        </div>
      `)}
    </div>
  `;
}

function MetricsPanel({result}) {
  const metrics = result.metrics || {};
  const finalValue = result.final_value;
  const cards = [
    ['策略收益', pct(metrics.total_return), palette.red],
    ['策略年化收益', pct(metrics.annual_return), palette.red],
    ['基准收益', pct(last(result.benchmark_return_values)), palette.gold],
    ['超额收益', pct(last(result.excess_return_values)), palette.red],
    ['夏普比率', fixed(metrics.sharpe_ratio, 3), '#1f2937'],
    ['最大回撤', pct(metrics.max_drawdown), '#1f2937'],
    ['胜率', pct(metrics.win_rate), '#1f2937'],
    ['盈亏比', fixed(metrics.profit_factor, 2), '#1f2937'],
    ['交易次数', intValue(metrics.total_trades), '#1f2937'],
    ['期末权益', money(finalValue), '#1f2937'],
  ];

  return html`
    <div className="panel-body">
      <h2>收益概述</h2>
      <div className="metrics-board">
        ${cards.map(([label, value, color]) => html`
          <div className="metric-tile" key=${label}>
            <span>${label}</span>
            <b style=${{color}}>${value}</b>
          </div>
        `)}
      </div>
      <div className="drawdown-panel">
        <h2>回撤曲线</h2>
        <${DrawdownChart} result=${result} />
      </div>
    </div>
  `;
}

function DrawdownChart({result}) {
  const ref = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!ref.current) {
      return undefined;
    }
    chartRef.current = echarts.init(ref.current, null, {renderer: 'canvas'});
    const resize = () => chartRef.current?.resize();
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current) {
      return;
    }
    chartRef.current.setOption(buildDrawdownOption(result || {}), {notMerge: true, lazyUpdate: true});
  }, [result]);

  return html`<div className="drawdown-canvas" ref=${ref}></div>`;
}

function TradesPanel({result}) {
  const closedTrades = (result.trades || []).map((trade) => ({...trade, status: trade.status || 'closed'}));
  const openPositions = (result.positions || []).map((position) => ({...position, status: 'open'}));
  const rows = [...openPositions, ...closedTrades];
  const orders = result.orders || [];

  return html`
    <div className="panel-body">
      <h2>交易记录</h2>
      <${DataCoverageNotice} result=${result} />
      <div className="trade-table-wrap">
        <table className="trade-table">
          <thead>
            <tr>
              ${['状态', '标的', '方向', '开仓日期', '平仓日期', '开仓价', '平仓/现价', '数量', '净利润', '持仓天数'].map((label) => html`
                <th key=${label}>${label}</th>
              `)}
            </tr>
          </thead>
          <tbody>
            ${rows.length ? rows.map((trade, index) => html`
              <tr key=${index}>
                <td><span className=${`trade-status ${trade.status}`}>${tradeStatus(trade.status)}</span></td>
                <td>${trade.data_name || '--'}</td>
                <td>${formatDirection(trade.direction)}</td>
                <td>${trade.entry_date || '--'}</td>
                <td>${trade.exit_date || (trade.status === 'open' ? '持仓中' : '--')}</td>
                <td>${fixed(trade.entry_price, 3)}</td>
                <td>${fixed(trade.exit_price ?? trade.last_price, 3)}</td>
                <td>${fixed(trade.size, 0)}</td>
                <td className=${Number(trade.net_pnl || 0) >= 0 ? 'positive' : 'negative'}>${fixed(trade.net_pnl, 2)}</td>
                <td>${trade.duration === '' ? '--' : fixed(trade.duration, 0)}</td>
              </tr>
            `) : html`
              <tr><td colSpan="10" className="empty-cell">暂无交易记录</td></tr>
            `}
          </tbody>
        </table>
      </div>
      <h2 className="section-heading">订单流水</h2>
      <div className="trade-table-wrap">
        <table className="trade-table">
          <thead>
            <tr>
              ${['日期', '标的', '方向', '状态', '委托数量', '成交数量', '委托价', '成交价', '成交额', '佣金'].map((label) => html`
                <th key=${label}>${label}</th>
              `)}
            </tr>
          </thead>
          <tbody>
            ${orders.length ? orders.map((order) => html`
              <tr key=${order.ref}>
                <td>${order.date || order.created_date || '--'}</td>
                <td>${order.data_name || '--'}</td>
                <td>${formatDirection(order.type)}</td>
                <td><span className=${`order-status ${String(order.status || '').toLowerCase()}`}>${orderStatusText(order.status)}</span></td>
                <td>${fixed(order.created_size, 0)}</td>
                <td>${fixed(order.executed_size, 0)}</td>
                <td>${fixed(order.created_price, 3)}</td>
                <td>${fixed(order.executed_price, 3)}</td>
                <td>${fixed(order.value, 2)}</td>
                <td>${fixed(order.commission, 2)}</td>
              </tr>
            `) : html`
              <tr><td colSpan="10" className="empty-cell">暂无订单流水</td></tr>
            `}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function DataCoverageNotice({result}) {
  const requestedStart = result.requested_start_date || '';
  const actualStart = result.nav_dates?.[0] || '';
  const late = (result.data_coverage || [])
    .filter((item) => daysBetween(requestedStart, item.start) > 30)
    .slice(0, 6);
  const actualDelay = daysBetween(requestedStart, actualStart);

  if (!requestedStart && !actualStart && !late.length) {
    return null;
  }

  return html`
    <div className=${actualDelay > 10 ? 'coverage-note warning' : 'coverage-note'}>
      <span>回测区间 ${requestedStart || '--'} 至 ${result.requested_end_date || '--'}，净值起始 ${actualStart || '--'}</span>
      ${late.length ? html`
        <b>晚于起始日期上市/可用：${late.map((item) => `${item.code} ${item.start}`).join('，')}</b>
      ` : null}
    </div>
  `;
}

function LogsPanel({logs, activityLog}) {
  const strategyLogs = logs || [];
  return html`
    <div className="panel-body">
      <h2>日志输出</h2>
      <div className="log-grid">
        <div className="log-box">
          <h3>策略日志</h3>
          ${strategyLogs.length ? html`
            <div className="log-table">
              ${strategyLogs.map((item, index) => html`
                <div className="log-row" key=${index}>
                  <span>${item.date || '--'}</span>
                  <b className=${`log-level ${item.level || 'info'}`}>${logLevelText(item.level)}</b>
                  <em>${item.message || ''}</em>
                </div>
              `)}
            </div>
          ` : html`<div className="empty-block">暂无策略日志。策略中的 print/log 输出会在下一次回测后显示在这里。</div>`}
        </div>
        <div className="log-box">
          <h3>系统日志</h3>
          <pre>${(activityLog || []).join('\n')}</pre>
        </div>
      </div>
    </div>
  `;
}

function buildReturnOption(result, toggles, compareSeries = [], chartRange = 'all') {
  const series = [];
  const axisColor = '#7a8798';
  const gridColor = '#e8edf4';
  const strategyReturnDates = result.strategy_return_dates?.length
    ? result.strategy_return_dates
    : result.nav_dates;
  const strategyReturnValues = result.strategy_return_values?.length
    ? result.strategy_return_values
    : navValuesToReturns(result.nav_values || []);

  function addReturnLine(key, dates, values, name, color, style = {}) {
    if (!toggles.includes(key) || !dates?.length || !values?.length) {
      return;
    }
    const item = {
      name,
      type: 'line',
      xAxisIndex: 0,
      yAxisIndex: 0,
      data: toPairs(dates, values),
      showSymbol: false,
      smooth: Boolean(style.smooth),
      sampling: 'lttb',
      connectNulls: true,
      z: style.z || 4,
      lineStyle: {
        width: style.width || 2,
        color,
        type: style.type || 'solid',
        opacity: style.opacity || 1,
      },
      itemStyle: {color},
      emphasis: {focus: 'series', lineStyle: {width: (style.width || 2) + 0.8}},
    };
    if (style.area) {
      item.areaStyle = {
        opacity: 0.16,
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          {offset: 0, color: style.areaColor || color},
          {offset: 1, color: 'rgba(255,255,255,0)'},
        ]),
      };
    }
    if (style.zeroLine) {
      item.markLine = zeroMarkLine();
    }
    series.push(item);
  }

  function addNavLine() {
    if (!toggles.includes('strategy_nav') || !result.nav_dates?.length || !result.nav_values?.length) {
      return;
    }
    series.push({
      name: '策略净值',
      type: 'line',
      xAxisIndex: 0,
      yAxisIndex: 1,
      data: toPairs(result.nav_dates, result.nav_values),
      showSymbol: false,
      sampling: 'lttb',
      connectNulls: true,
      z: 3,
      lineStyle: {width: 1.7, color: palette.green, type: 'dashed', opacity: 0.9},
      itemStyle: {color: palette.green},
      emphasis: {focus: 'series'},
    });
  }

  addReturnLine('strategy_return', strategyReturnDates, strategyReturnValues,
    '策略收益', palette.blue, {width: 3, area: true, areaColor: 'rgba(53, 100, 168, 0.24)', zeroLine: true, z: 8});
  addReturnLine('benchmark_return', result.benchmark_return_dates, result.benchmark_return_values,
    benchmarkLabel(result), palette.slate, {type: 'dashed', width: 2.1, z: 5});
  addReturnLine('excess_return', result.excess_return_dates, result.excess_return_values,
    '超额收益', palette.gold, {width: 2, z: 6});
  addNavLine();

  const colorCycle = [palette.violet, palette.cyan, '#8c6d4f', '#536f9f', '#b85b4b'];
  for (const [index, item] of (result.underlying_series || []).entries()) {
    const color = colorCycle[index % colorCycle.length];
    addReturnLine('underlying_price', item.dates, normalizedToReturns(item.normalized),
      `${item.name} 价格收益`, color, {type: 'dotted', width: 1.5, opacity: 0.88});
    addReturnLine('underlying_return', item.dates, item.returns,
      `${item.name} 收益`, color, {type: 'dashed', width: 1.5, opacity: 0.88});
  }

  const compareColors = ['#0f766e', '#b7791f', '#7c3aed', '#be123c', '#2563eb', '#5f6f83'];
  for (const [index, item] of (compareSeries || []).entries()) {
    const color = compareColors[index % compareColors.length];
    addReturnLine('compare_return', item.dates, item.returns,
      `${item.name || item.code} 对比收益`, color, {width: 1.9, opacity: 0.92});
  }

  if (toggles.includes('signals') && result.signals?.length) {
    const strategyReturnByDate = new Map((strategyReturnDates || []).map((date, index) => [date, strategyReturnValues?.[index]]));
    for (const type of ['buy', 'sell']) {
      const points = result.signals
        .filter((item) => item.type === type && strategyReturnByDate.has(item.date))
        .map((item) => [item.date, strategyReturnByDate.get(item.date), item.data_name || '', item.price, item.size]);
      if (points.length) {
        series.push({
          name: type === 'buy' ? '买入信号' : '卖出信号',
          type: 'scatter',
          xAxisIndex: 0,
          yAxisIndex: 0,
          data: points,
          symbol: 'triangle',
          symbolRotate: type === 'buy' ? 0 : 180,
          symbolSize: 12,
          symbolOffset: [0, type === 'buy' ? -9 : 9],
          z: 12,
          itemStyle: {color: type === 'buy' ? palette.green : palette.red, borderColor: '#fff', borderWidth: 1.5},
          tooltip: {
            formatter: (params) => `${params.seriesName}<br/>日期: ${params.value[0]}<br/>标的: ${params.value[2]}<br/>价格: ${formatNumber(params.value[3], 3)}<br/>数量: ${formatNumber(Math.abs(params.value[4] || 0), 0)}`,
          },
        });
      }
    }
  }

  const drawdown = calcDrawdownPercent(result.nav_values || []);
  if (result.nav_dates?.length && drawdown.length) {
    series.push({
      name: '策略回撤',
      type: 'line',
      xAxisIndex: 1,
      yAxisIndex: 2,
      data: toPairs(result.nav_dates, drawdown),
      showSymbol: false,
      sampling: 'lttb',
      connectNulls: true,
      lineStyle: {color: palette.red, width: 1.2},
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          {offset: 0, color: 'rgba(217, 89, 76, 0.30)'},
          {offset: 1, color: 'rgba(217, 89, 76, 0.04)'},
        ]),
      },
      itemStyle: {color: palette.red},
      markLine: zeroMarkLine(),
    });
  }

  const hasData = series.some((item) => item.data?.length);
  const hasNavAxis = toggles.includes('strategy_nav') && result.nav_values?.length;
  const chartWindow = getChartWindow(
    collectChartDates(result, compareSeries),
    chartRange,
  );

  return {
    color: Object.values(palette),
    animationDuration: 260,
    animationEasing: 'cubicOut',
    tooltip: {
      trigger: 'axis',
      axisPointer: {type: 'cross', link: [{xAxisIndex: [0, 1]}], label: {backgroundColor: '#25324a'}},
      borderWidth: 0,
      backgroundColor: 'rgba(16, 24, 40, 0.92)',
      textStyle: {color: '#fff', fontSize: 12},
      extraCssText: 'box-shadow:0 10px 28px rgba(16,24,40,.22);border-radius:6px;',
      formatter: formatReturnTooltip,
    },
    legend: {
      type: 'scroll',
      top: 0,
      left: 4,
      right: 42,
      itemWidth: 18,
      itemHeight: 8,
      textStyle: {color: '#536071', fontWeight: 700},
    },
    toolbox: {
      right: 4,
      top: 0,
      itemSize: 14,
      feature: {
        restore: {title: '还原'},
        saveAsImage: {title: '保存'},
      },
    },
    grid: [
      {left: 62, right: hasNavAxis ? 70 : 34, top: 48, height: '62%', containLabel: false},
      {left: 62, right: hasNavAxis ? 70 : 34, top: '78%', height: '13%', containLabel: false},
    ],
    xAxis: [
      {
        type: 'time',
        gridIndex: 0,
        boundaryGap: false,
        axisLine: {lineStyle: {color: '#ccd6e3'}},
        axisTick: {show: false},
        axisLabel: {color: axisColor, hideOverlap: true},
        splitLine: {show: true, lineStyle: {color: gridColor}},
      },
      {
        type: 'time',
        gridIndex: 1,
        boundaryGap: false,
        axisLine: {lineStyle: {color: '#ccd6e3'}},
        axisTick: {show: false},
        axisLabel: {color: axisColor, hideOverlap: true},
        splitLine: {show: true, lineStyle: {color: gridColor}},
      },
    ],
    yAxis: [
      {
        type: 'value',
        gridIndex: 0,
        name: '累计收益',
        scale: true,
        axisLabel: {formatter: formatAxisPercent, color: axisColor},
        axisLine: {show: false},
        axisTick: {show: false},
        splitLine: {lineStyle: {color: gridColor}},
      },
      {
        type: 'value',
        gridIndex: 0,
        name: '净值',
        position: 'right',
        show: Boolean(hasNavAxis),
        scale: true,
        axisLabel: {formatter: (value) => formatNumber(value, 2), color: axisColor},
        axisLine: {show: false},
        axisTick: {show: false},
        splitLine: {show: false},
      },
      {
        type: 'value',
        gridIndex: 1,
        name: '回撤',
        max: 0,
        axisLabel: {formatter: formatAxisPercent, color: axisColor},
        axisLine: {show: false},
        axisTick: {show: false},
        splitLine: {lineStyle: {color: gridColor}},
      },
    ],
    axisPointer: {link: [{xAxisIndex: [0, 1]}]},
    dataZoom: [
      {type: 'inside', xAxisIndex: [0, 1], filterMode: 'none', ...chartWindow},
      {
        type: 'slider',
        xAxisIndex: [0, 1],
        height: 20,
        bottom: 4,
        borderColor: '#d7dee9',
        fillerColor: 'rgba(53, 100, 168, 0.14)',
        handleStyle: {color: '#3564a8'},
        textStyle: {color: axisColor},
        filterMode: 'none',
        ...chartWindow,
      },
    ],
    series,
    graphic: hasData ? [] : [{
      type: 'text',
      left: 'center',
      top: '42%',
      style: {text: '暂无回测数据，运行后将实时加载标准收益图', fill: '#98a3b3', fontSize: 15, fontWeight: 600},
    }],
  };
}

function buildSignalOption(analysis) {
  const timeline = analysis.timeline || [];
  const dates = timeline.map((item) => item.date);
  const hasData = dates.length > 0;

  return {
    animationDuration: 260,
    tooltip: {trigger: 'axis'},
    legend: {top: 0, right: 8, textStyle: {color: '#536071'}},
    grid: {left: 54, right: 50, top: 42, bottom: 36},
    xAxis: {type: 'category', data: dates, splitLine: {show: true, lineStyle: {color: '#edf1f6'}}},
    yAxis: [
      {type: 'value', name: '信号次数', splitLine: {lineStyle: {color: '#edf1f6'}}},
      {type: 'value', name: '净信号', splitLine: {show: false}},
    ],
    series: [
      {name: '买入信号', type: 'bar', data: timeline.map((item) => item.buy), itemStyle: {color: palette.green}},
      {name: '卖出信号', type: 'bar', data: timeline.map((item) => -item.sell), itemStyle: {color: palette.red}},
      {name: '净信号累积', type: 'line', yAxisIndex: 1, data: timeline.map((item) => item.exposure), itemStyle: {color: palette.gold}, lineStyle: {width: 2}},
    ],
    graphic: hasData ? [] : [{
      type: 'text',
      left: 'center',
      top: 'middle',
      style: {text: '暂无信号数据', fill: '#98a3b3', fontSize: 14, fontWeight: 600},
    }],
  };
}

function buildDrawdownOption(result) {
  const dates = result.nav_dates || [];
  const drawdown = calcDrawdownPercent(result.nav_values || []);

  return {
    animationDuration: 260,
    tooltip: {
      trigger: 'axis',
      axisPointer: {type: 'cross', label: {backgroundColor: '#25324a'}},
      borderWidth: 0,
      backgroundColor: 'rgba(16, 24, 40, 0.92)',
      textStyle: {color: '#fff', fontSize: 12},
      valueFormatter: (value) => `${formatNumber(value, 2)}%`,
    },
    grid: {left: 58, right: 26, top: 18, bottom: 36},
    xAxis: {
      type: 'time',
      boundaryGap: false,
      axisTick: {show: false},
      axisLabel: {color: '#7a8798'},
      splitLine: {show: true, lineStyle: {color: '#e8edf4'}},
    },
    yAxis: {
      type: 'value',
      name: '回撤',
      max: 0,
      axisTick: {show: false},
      axisLabel: {formatter: formatAxisPercent, color: '#7a8798'},
      splitLine: {lineStyle: {color: '#e8edf4'}},
    },
    series: [{
      name: '回撤',
      type: 'line',
      data: toPairs(dates, drawdown),
      showSymbol: false,
      sampling: 'lttb',
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          {offset: 0, color: 'rgba(217, 89, 76, 0.30)'},
          {offset: 1, color: 'rgba(217, 89, 76, 0.04)'},
        ]),
      },
      lineStyle: {color: palette.red, width: 1.6},
      itemStyle: {color: palette.red},
      markLine: zeroMarkLine(),
    }],
    graphic: dates.length ? [] : [{
      type: 'text',
      left: 'center',
      top: 'middle',
      style: {text: '暂无数据', fill: '#98a3b3', fontSize: 14, fontWeight: 600},
    }],
  };
}

async function loadMeta() {
  return fetchJson(`${API_BASE}/meta`);
}

async function fetchJson(url, options = {}) {
  const headers = options.body instanceof FormData ? {} : {'Content-Type': 'application/json'};
  const response = await fetch(url, {...options, headers: {...headers, ...(options.headers || {})}});
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `请求失败: ${response.status}`);
  }
  return payload;
}

function coerceParams(schema, params) {
  const output = {};
  for (const item of schema) {
    const value = params[item.name];
    if (item.type === 'bool') {
      output[item.name] = Boolean(value);
    } else if (item.type === 'int') {
      output[item.name] = Number.parseInt(value, 10);
    } else if (item.type === 'float') {
      output[item.name] = Number.parseFloat(value);
    } else {
      output[item.name] = value;
    }
    if (Number.isNaN(output[item.name])) {
      output[item.name] = item.default;
    }
  }
  return output;
}

function mergeBacktestResult(current = {}, incoming = {}) {
  if (!incoming || !incoming.partial) {
    return incoming || {};
  }

  const merged = {...current, ...incoming};
  for (const key of [
    'underlying_series',
    'underlying_dates',
    'underlying_prices',
    'benchmark_dates',
    'benchmark_values',
    'benchmark_return_dates',
    'benchmark_return_values',
    'excess_return_dates',
    'excess_return_values',
    'signals',
    'trades',
    'positions',
    'orders',
    'logs',
    'data_coverage',
  ]) {
    if ((!incoming[key] || !incoming[key].length) && current[key]?.length) {
      merged[key] = current[key];
    }
  }
  merged.metrics = {...(current.metrics || {}), ...(incoming.metrics || {})};
  return merged;
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  if (mins >= 60) {
    const hours = Math.floor(mins / 60);
    const rest = mins % 60;
    return `${hours}:${String(rest).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function runtimeText(isRunning, seconds) {
  const elapsed = Number(seconds) || 0;
  if (isRunning) {
    return `用时 ${formatDuration(elapsed)}`;
  }
  return elapsed > 0 ? `耗时 ${formatDuration(elapsed)}` : '待运行';
}

function progressLabel(progress = {}) {
  if (!progress || progress.stage === 'idle') {
    return '';
  }
  if (progress.current_date) {
    return `增量绘制 ${progress.current_date}${progress.bars ? ` · ${progress.bars} bars` : ''}`;
  }
  if (progress.stage === 'loading') {
    if (progress.total) {
      return `行情加载 ${progress.loaded || 0}/${progress.total}`;
    }
    return '行情加载中';
  }
  if (progress.stage === 'queued') {
    return '等待执行';
  }
  if (progress.stage === 'done') {
    return '已完成';
  }
  return '';
}

function validateRunConfig({startDate, endDate, initialCash, commission}) {
  if (!startDate || !endDate) {
    return '请选择完整回测日期';
  }
  if (new Date(startDate) > new Date(endDate)) {
    return '开始日期不能晚于结束日期';
  }
  const cash = Number(initialCash);
  if (!Number.isFinite(cash) || cash <= 0) {
    return '初始资金必须大于0';
  }
  const commissionValue = Number(commission);
  if (!Number.isFinite(commissionValue) || commissionValue < 0) {
    return '佣金费率不能为负数';
  }
  return '';
}

function toPairs(dates = [], values = []) {
  return dates.map((date, index) => [date, values[index]]).filter((item) => item[1] !== null && item[1] !== undefined);
}

function hasResultData(result = {}) {
  return Boolean(
    result.nav_dates?.length
    || result.strategy_return_dates?.length
    || result.underlying_series?.length
    || result.trades?.length
    || result.signals?.length
  );
}

function collectChartDates(result = {}, compareSeries = []) {
  const dates = [
    ...(result.strategy_return_dates || []),
    ...(result.nav_dates || []),
    ...(result.benchmark_return_dates || []),
    ...(result.excess_return_dates || []),
  ];
  for (const item of result.underlying_series || []) {
    dates.push(...(item.dates || []));
  }
  for (const item of compareSeries || []) {
    dates.push(...(item.dates || []));
  }
  return [...new Set(dates)].sort();
}

function getChartWindow(dates = [], range = 'all') {
  if (!dates.length || range === 'all') {
    return {};
  }

  const end = new Date(dates[dates.length - 1]);
  const start = new Date(end);
  if (range === '1m') {
    start.setMonth(start.getMonth() - 1);
  } else if (range === '3m') {
    start.setMonth(start.getMonth() - 3);
  } else if (range === '6m') {
    start.setMonth(start.getMonth() - 6);
  } else if (range === 'ytd') {
    start.setMonth(0, 1);
  }

  const startValue = start.toISOString().slice(0, 10);
  return {startValue, endValue: dates[dates.length - 1]};
}

function navValuesToReturns(values = []) {
  if (!values.length) {
    return [];
  }
  const base = Number(values[0]) || 1;
  return values.map((value) => roundNumber((Number(value) / base - 1) * 100, 4));
}

function normalizedToReturns(values = []) {
  return (values || []).map((value) => roundNumber((Number(value) - 1) * 100, 4));
}

function calcDrawdownPercent(values = []) {
  let peak = Number(values[0]) || 1;
  return (values || []).map((value) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return null;
    }
    peak = Math.max(peak, numeric);
    return peak ? roundNumber((numeric / peak - 1) * 100, 4) : 0;
  });
}

function zeroMarkLine() {
  return {
    silent: true,
    symbol: 'none',
    label: {show: false},
    lineStyle: {color: '#cfd8e4', width: 1, type: 'dashed'},
    data: [{yAxis: 0}],
  };
}

function formatReturnTooltip(params = []) {
  const items = Array.isArray(params) ? params : [params];
  const visible = items.filter((item) => item && item.value && item.value[1] !== null && item.value[1] !== undefined);
  if (!visible.length) {
    return '';
  }

  const date = visible[0].axisValueLabel || visible[0].value?.[0] || '';
  const rows = visible.map((item) => {
    const value = Array.isArray(item.value) ? item.value[1] : item.value;
    if (item.seriesType === 'scatter') {
      return `<div>${item.marker}${item.seriesName}: ${item.value[2] || '--'} / ${formatNumber(item.value[3], 3)}</div>`;
    }
    const isNav = item.seriesName === '策略净值';
    const formatted = isNav ? formatNumber(value, 3) : `${formatNumber(value, Math.abs(Number(value)) >= 100 ? 1 : 2)}%`;
    return `<div>${item.marker}${item.seriesName}: <b>${formatted}</b></div>`;
  }).join('');

  return `<div class="chart-tooltip"><div class="chart-tooltip-date">${date}</div>${rows}</div>`;
}

function formatAxisPercent(value) {
  return `${formatNumber(value, Math.abs(Number(value)) >= 100 ? 0 : 1)}%`;
}

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '--';
  }
  return Number(value).toFixed(digits);
}

function roundNumber(value, digits = 4) {
  if (!Number.isFinite(value)) {
    return null;
  }
  const base = 10 ** digits;
  return Math.round(value * base) / base;
}

function metricTone(label, value) {
  if (label === '交易次数') {
    return 'neutral';
  }
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return 'neutral';
  }
  if (label === '最大回撤') {
    return number < 0 ? 'negative' : 'neutral';
  }
  if (number > 0) {
    return 'positive';
  }
  if (number < 0) {
    return 'negative';
  }
  return 'neutral';
}

function toCsv(rows, columns) {
  const header = columns.join(',');
  const body = rows.map((row) => columns.map((column) => csvCell(row[column])).join(','));
  return `\ufeff${[header, ...body].join('\n')}`;
}

function csvCell(value) {
  const text = value === null || value === undefined ? '' : String(value);
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function downloadText(filename, text, type) {
  const blob = new Blob([text], {type});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function toggleValue(values, value) {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

function parseSymbolInput(value) {
  return String(value || '')
    .split(/[\s,，;；]+/)
    .map((item) => {
      const match = item.match(/\d{6}/);
      return match ? match[0] : '';
    })
    .filter(Boolean)
    .filter((item, index, values) => values.indexOf(item) === index);
}

function mergeSeries(current, incoming) {
  const byCode = new Map((current || []).map((item) => [item.code, item]));
  for (const item of incoming || []) {
    byCode.set(item.code, item);
  }
  return Array.from(byCode.values());
}

function benchmarkLabel(result) {
  const source = result.benchmark_source || '';
  if (source.startsWith('proxy:')) {
    return `基准收益 (${source.split(':')[1]}代用)`;
  }
  return '基准收益';
}

function pct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '--';
  }
  return `${Number(value).toFixed(2)}%`;
}

function fixed(value, digits) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '--';
  }
  return Number(value).toFixed(digits);
}

function intValue(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '--';
  }
  return String(Math.trunc(Number(value)));
}

function money(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '--';
  }
  return Number(value).toLocaleString('zh-CN', {maximumFractionDigits: 0});
}

function last(values) {
  return Array.isArray(values) && values.length ? values[values.length - 1] : null;
}

function daysBetween(start, end) {
  if (!start || !end) {
    return 0;
  }
  const startTime = new Date(start).getTime();
  const endTime = new Date(end).getTime();
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime)) {
    return 0;
  }
  return Math.round((endTime - startTime) / 86400000);
}

function formatDirection(direction) {
  if (['buy', 'Buy', 'BUY'].includes(direction)) {
    return '买入';
  }
  if (['sell', 'Sell', 'SELL'].includes(direction)) {
    return '卖出';
  }
  if (['Long', 'long', '多头'].includes(direction)) {
    return '多头';
  }
  if (['Short', 'short', '空头'].includes(direction)) {
    return '空头';
  }
  return direction || '--';
}

function tradeStatus(status) {
  if (status === 'open') {
    return '持仓中';
  }
  if (status === 'closed') {
    return '已平仓';
  }
  return status || '--';
}

function orderStatusText(status) {
  const map = {
    Submitted: '已提交',
    Accepted: '已接受',
    Partial: '部分成交',
    Completed: '已成交',
    Canceled: '已撤销',
    Cancelled: '已撤销',
    Expired: '已过期',
    Margin: '保证金不足',
    Rejected: '已拒绝',
  };
  return map[status] || status || '--';
}

function logLevelText(level) {
  const map = {
    info: 'INFO',
    warn: 'WARN',
    warning: 'WARN',
    error: 'ERROR',
    debug: 'DEBUG',
  };
  return map[level] || String(level || 'info').toUpperCase();
}

function taskStatus(status) {
  if (status === 'running') {
    return '运行中';
  }
  if (status === 'done') {
    return '完成';
  }
  if (status === 'error') {
    return '失败';
  }
  return status || '--';
}

createRoot(document.getElementById('root')).render(html`<${App} />`);
