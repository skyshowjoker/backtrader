import {html} from '../constants.js';
import {fixed, money} from '../utils/formatters.js';

export default function MetricsPanel({result}) {
  const metrics = result?.metrics || {};

  return html`
    <div className="metrics-panel">
      <h2>绩效指标</h2>
      <div className="metrics-grid">
        <div className="metric-card"><span>总收益</span><b>${pct(metrics.total_return)}</b></div>
        <div className="metric-card"><span>年化收益</span><b>${pct(metrics.annual_return)}</b></div>
        <div className="metric-card"><span>夏普比率</span><b>${fixed(metrics.sharpe_ratio, 3)}</b></div>
        <div className="metric-card"><span>最大回撤</span><b>${pct(metrics.max_drawdown)}</b></div>
        <div className="metric-card"><span>总交易</span><b>${metrics.total_trades || 0}</b></div>
        <div className="metric-card"><span>胜率</span><b>${pct(metrics.win_rate)}</b></div>
        <div className="metric-card"><span>盈亏比</span><b>${fixed(metrics.profit_factor, 2)}</b></div>
        <div className="metric-card"><span>期末权益</span><b>${money(result?.final_value)}</b></div>
      </div>
      <h2 style="margin-top:24px">回撤曲线</h2>
      <${DrawdownChart} result=${result} />
    </div>
  `;
}

function pct(v) { return v == null || Number.isNaN(+v) ? '--' : `${(+v).toFixed(2)}%`; }

import DrawdownChart from './DrawdownChart.js';
