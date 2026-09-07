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

function formatAxisPercent(value) {
  return `${formatNumber(value, Math.abs(Number(value)) >= 100 ? 0 : 1)}%`;
}

export {
  pct, fixed, intValue, money, last,
  formatNumber, roundNumber, daysBetween,
  metricTone, formatDirection, tradeStatus,
  orderStatusText, logLevelText, taskStatus,
  formatDuration, formatAxisPercent,
};
