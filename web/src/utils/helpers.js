import {API_BASE} from '../constants.js';
import {roundNumber, formatNumber} from './formatters.js';

async function fetchJson(url, options = {}) {
  const headers = options.body instanceof FormData ? {} : {'Content-Type': 'application/json'};
  const response = await fetch(url, {...options, headers: {...headers, ...(options.headers || {})}});
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `请求失败: ${response.status}`);
  }
  return payload;
}

async function loadMeta() {
  return fetchJson(`${API_BASE}/meta`);
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

function validateRunConfig(config = {}) {
  const startDate = config.start_date || config.startDate;
  const endDate = config.end_date || config.endDate;
  const {initial_cash: initialCashSnake, initialCash, commission} = config;
  const cashInput = initialCashSnake ?? initialCash;
  if (!startDate || !endDate) {
    return '请选择完整回测日期';
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate) || !/^\d{4}-\d{2}-\d{2}$/.test(endDate)) {
    return '回测日期格式无效';
  }
  if (startDate > endDate) {
    return '开始日期不能晚于结束日期';
  }
  const cash = Number(cashInput);
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

function runtimeText(isRunning, seconds) {
  const elapsed = Number(seconds) || 0;
  if (isRunning) {
    return `用时 ${formatDuration(elapsed)}`;
  }
  return elapsed > 0 ? `耗时 ${formatDuration(elapsed)}` : '待运行';
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

export {
  fetchJson, loadMeta, coerceParams, mergeBacktestResult,
  validateRunConfig, toPairs, hasResultData, collectChartDates,
  getChartWindow, navValuesToReturns, normalizedToReturns,
  calcDrawdownPercent, toggleValue, parseSymbolInput,
  mergeSeries, benchmarkLabel, progressLabel, runtimeText,
};
