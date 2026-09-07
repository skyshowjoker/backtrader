import {html, useState, useEffect, useMemo, createRoot} from './constants.js';
import {DEFAULT_TOGGLES, chartRangeOptions, API_BASE} from './constants.js';
import {fetchJson, loadMeta, toggleValue, parseSymbolInput, mergeSeries, coerceParams} from './utils/helpers.js';
import {exportBacktestJson, exportTradesCsv, exportSignalsCsv} from './utils/exporters.js';
import useBacktest from './hooks/useBacktest.js';

import TopNav from './components/TopNav.js';
import RunToolbar from './components/RunToolbar.js';
import Sidebar from './components/Sidebar.js';
import OverviewPanel from './components/OverviewPanel.js';
import OverviewKpis from './components/OverviewKpis.js';
import MetricsPanel from './components/MetricsPanel.js';
import TradesPanel from './components/TradesPanel.js';
import LogsPanel from './components/LogsPanel.js';
import TaskTable from './components/TaskTable.js';

function App() {
  const [meta, setMeta] = useState({strategies: [], etfs: [], benchmarks: []});
  const [strategyName, setStrategyName] = useState('');
  const [params, setParams] = useState({});
  const [dataCodes, setDataCodes] = useState(['510300']);
  const [benchmark, setBenchmark] = useState('000300');
  const [startDate, setStartDate] = useState('2020-01-01');
  const [endDate, setEndDate] = useState('2025-12-31');
  const [initialCash, setInitialCash] = useState('1000000');
  const [commission, setCommission] = useState('0.0002');
  const [frequency, setFrequency] = useState('daily');
  const [activeTab, setActiveTab] = useState('回测');
  const [chartRange, setChartRange] = useState('all');
  const [compareInput, setCompareInput] = useState('');
  const [compareSeries, setCompareSeries] = useState([]);
  const [compLoading, setCompLoading] = useState(false);

  // Upload state
  const [strategyFormat, setStrategyFormat] = useState('auto');
  const [strategySource, setStrategySource] = useState('');
  const [sourceFilename, setSourceFilename] = useState('custom_strategy.py');

  const bt = useBacktest();

  // Load meta on mount
  useEffect(() => {
    loadMeta().then(p => {
      setMeta(p);
      setStrategyName(p.defaults?.strategy || p.strategies?.[0]?.name || '');
      setDataCodes(p.defaults?.data_codes || ['510300']);
      setBenchmark(p.defaults?.benchmark || '000300');
    }).catch(e => bt.setRunStatus({type: 'error', text: e.message}));
  }, []);

  const selectedStrategy = useMemo(() =>
    meta.strategies.find(s => s.name === strategyName),
    [meta.strategies, strategyName]
  );

  // Sync params when strategy changes
  useEffect(() => {
    if (!selectedStrategy) return;
    const next = {};
    for (const p of selectedStrategy.params || []) next[p.name] = p.default;
    setParams(next);
    if (selectedStrategy.preferred_data_codes?.length)
      setDataCodes(selectedStrategy.preferred_data_codes);
  }, [selectedStrategy?.name]);

  const handleRun = () => bt.runBacktest(strategyName,
    coerceParams(selectedStrategy?.params || [], params),
    {start_date: startDate, end_date: endDate, initial_cash: initialCash,
     commission, benchmark, data_codes: dataCodes, frequency, data_type: 'etf'}
  );

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const body = new FormData();
    body.append('file', file);
    body.append('strategy_format', strategyFormat);
    try {
      const r = await fetchJson(`${API_BASE}/strategies/upload`, {method: 'POST', body});
      setMeta(prev => ({...prev, strategies: r.strategies}));
      setStrategyName(r.strategy);
      bt.appendLog(`上传策略: ${r.strategy}`);
    } catch (err) { bt.setRunStatus({type: 'error', text: err.message}); }
    e.target.value = '';
  };

  const addCompare = async () => {
    const codes = parseSymbolInput(compareInput);
    if (!codes.length) return;
    setCompLoading(true);
    try {
      const r = await fetchJson(`${API_BASE}/market/series?${new URLSearchParams({codes: codes.join(','), start_date: startDate, end_date: endDate})}`);
      if (r.series?.length) {
        setCompareSeries(prev => mergeSeries(prev, r.series));
        setCompareInput('');
      }
    } catch (err) { bt.setRunStatus({type: 'error', text: err.message}); }
    setCompLoading(false);
  };

  return html`
    <div className="shell">
      <${TopNav} />
      <${RunToolbar}
        startDate=${startDate} setStartDate=${setStartDate}
        endDate=${endDate} setEndDate=${setEndDate}
        initialCash=${initialCash} setInitialCash=${setInitialCash}
        commission=${commission} setCommission=${setCommission}
        benchmark=${benchmark} setBenchmark=${setBenchmark}
        benchmarks=${meta.benchmarks}
        frequency=${frequency} setFrequency=${setFrequency}
        isRunning=${bt.isRunning} elapsed=${bt.elapsedSeconds}
        progress=${bt.runProgress} runStatus=${bt.runStatus}
        onRun=${handleRun} />
      <div className="app-body">
        <${Sidebar}
          strategies=${meta.strategies} selectedStrategy=${selectedStrategy}
          strategyName=${strategyName} setStrategyName=${setStrategyName}
          params=${params} setParams=${setParams}
          etfs=${meta.etfs} dataCodes=${dataCodes} setDataCodes=${setDataCodes}
          strategyFormat=${strategyFormat} setStrategyFormat=${setStrategyFormat}
          onUpload=${handleUpload} />
        <div className="main-content">
          <div className="tabs">
            ${['回测', '归因分析', '交易记录', '日志'].map(t => html`
              <button key=${t} className=${activeTab === t ? 'active' : ''}
                onClick=${() => setActiveTab(t)}>${t}</button>
            `)}
          </div>
          ${activeTab === '回测' && html`
            <div className="panel">
              <${OverviewKpis} result=${bt.result} isRunning=${bt.isRunning} runStatus=${bt.runStatus} />
              <div className="compare-row">
                <input value=${compareInput} placeholder="添加对比标的: 510300,159915"
                  onInput=${e => setCompareInput(e.target.value)}
                  onKeyDown=${e => e.key === 'Enter' && addCompare()} />
                <button onClick=${addCompare} disabled=${compLoading}>添加</button>
                ${compareSeries.map(s => html`
                  <span key=${s.code} className="compare-tag" onClick=${() => setCompareSeries(prev => prev.filter(x => x.code !== s.code))}>
                    ${s.code} ${s.name || ''} ✕
                  </span>
                `)}
              </div>
              <${OverviewPanel} result=${bt.result} compareSeries=${compareSeries}
                chartRange=${chartRange} setChartRange=${setChartRange} />
              <div className="export-bar">
                <button onClick=${() => exportBacktestJson(bt.result, bt.setRunStatus)}>导出JSON</button>
                <button onClick=${() => exportTradesCsv(bt.result, bt.setRunStatus)}>导出交易CSV</button>
                <button onClick=${() => exportSignalsCsv(bt.result, bt.setRunStatus)}>导出信号CSV</button>
                <button onClick=${bt.refreshTasks}>刷新任务</button>
              </div>
              <${TaskTable} tasks=${bt.taskHistory} openTask=${bt.openTask} />
            </div>
          `}
          ${activeTab === '归因分析' && html`<${MetricsPanel} result=${bt.result} />`}
          ${activeTab === '交易记录' && html`<${TradesPanel} result=${bt.result} />`}
          ${activeTab === '日志' && html`<${LogsPanel} result=${bt.result} />`}
        </div>
      </div>
    </div>
  `;
}

createRoot(document.getElementById('root')).render(html`<${App} />`);
