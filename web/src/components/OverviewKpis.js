import {html} from '../constants.js';

export default function OverviewKpis({result, isRunning, runStatus}) {
  const metrics = result?.metrics || {};
  const status = runStatus || {type: 'idle', text: '就绪'};

  const kpis = [
    ['策略收益', pct(metrics.total_return), metrics.total_return],
    ['年化收益', pct(metrics.annual_return), metrics.annual_return],
    ['超额收益', pct(last(result?.excess_return_values)), last(result?.excess_return_values)],
    ['最大回撤', pct(metrics.max_drawdown), -Math.abs(Number(metrics.max_drawdown || 0))],
    ['夏普比率', fixed(metrics.sharpe_ratio, 2), metrics.sharpe_ratio],
    ['交易次数', intValue(metrics.total_trades), metrics.total_trades],
  ];

  return html`
    <div className="overview-kpis">
      ${kpis.map(([label, value, raw]) => html`
        <div className="overview-kpi" key=${label}>
          <span>${label}</span>
          <b className=${tone(label, raw)}>${value}</b>
        </div>
      `)}
      <div className=${`overview-run-state ${isRunning ? 'running' : status.type}`}>
        <span>状态</span>
        <b>${status.text || '就绪'}</b>
      </div>
    </div>
  `;
}

function pct(v) { return v === null || v === undefined || Number.isNaN(Number(v)) ? '--' : `${Number(v).toFixed(2)}%`; }
function fixed(v, d) { return v === null || v === undefined || Number.isNaN(Number(v)) ? '--' : Number(v).toFixed(d); }
function intValue(v) { return v === null || v === undefined || Number.isNaN(Number(v)) ? '--' : String(Math.trunc(Number(v))); }
function last(v) { return Array.isArray(v) && v.length ? v[v.length - 1] : null; }
function tone(label, value) {
  if (label === '交易次数') return 'neutral';
  const n = Number(value);
  if (!Number.isFinite(n)) return 'neutral';
  if (label === '最大回撤') return n < 0 ? 'negative' : 'neutral';
  return n > 0 ? 'positive' : n < 0 ? 'negative' : 'neutral';
}
