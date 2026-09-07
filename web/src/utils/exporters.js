import {fixed} from './formatters.js';

function toCsv(rows, columns) {
  const header = columns.join(',');
  const body = rows.map((row) => columns.map((column) => csvCell(row[column])).join(','));
  return `﻿${[header, ...body].join('\n')}`;
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

function exportBacktestJson(result, setRunStatus) {
  if (!hasResultData(result)) {
    setRunStatus({type: 'error', text: '暂无可导出结果'});
    return;
  }
  downloadText(
    `backtest-${new Date().toISOString().slice(0, 10)}.json`,
    JSON.stringify(result, null, 2),
    'application/json',
  );
}

function exportTradesCsv(result, setRunStatus) {
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
}

function exportSignalsCsv(result, setRunStatus) {
  const signals = result.signals || [];
  if (!signals.length) {
    setRunStatus({type: 'error', text: '暂无策略信号'});
    return;
  }
  downloadText('signals.csv', toCsv(signals, ['date', 'type', 'data_name', 'price', 'size']), 'text/csv;charset=utf-8');
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

export {toCsv, csvCell, downloadText, exportBacktestJson, exportTradesCsv, exportSignalsCsv, hasResultData};
