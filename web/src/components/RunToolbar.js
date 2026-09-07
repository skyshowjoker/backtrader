import {html} from '../constants.js';
import {progressLabel, runtimeText} from '../utils/helpers.js';

export default function RunToolbar({
  startDate, setStartDate, endDate, setEndDate,
  initialCash, setInitialCash, commission, setCommission,
  benchmark, setBenchmark, benchmarks,
  frequency, setFrequency,
  isRunning, elapsed, progress,
  runStatus, onRun,
}) {
  const status = runStatus || {type: 'idle', text: '就绪'};

  return html`
    <section className="run-toolbar">
      <div className="run-settings">
        <span className="label">设置：</span>
        <input className="date-field" type="date" value=${startDate}
          onInput=${(e) => setStartDate(e.target.value)} />
        <span className="date-arrow">至</span>
        <input className="date-field" type="date" value=${endDate}
          onInput=${(e) => setEndDate(e.target.value)} />
        <span className="currency">¥</span>
        <input className="money-field" value=${initialCash}
          onInput=${(e) => setInitialCash(e.target.value)} inputMode="decimal" />
        <input className="commission-field" value=${commission}
          onInput=${(e) => setCommission(e.target.value)} inputMode="decimal" />
        <select value=${benchmark} onInput=${(e) => setBenchmark(e.target.value)}>
          ${(benchmarks || []).map((item) => html`
            <option key=${item.code} value=${item.code}>${item.label}</option>
          `)}
        </select>
        <select value=${frequency} onInput=${(e) => setFrequency(e.target.value)}>
          <option value="daily">每天</option>
          <option value="weekly">每周</option>
          <option value="monthly">每月</option>
        </select>
        <span className="python-badge">Python3</span>
      </div>
      <div className="run-actions">
        <div className="run-runtime">
          <span className=${`status ${status.type}`}>${status.text}</span>
          <b>${runtimeText(isRunning, elapsed)}</b>
          ${progressLabel(progress) ? html`<em>${progressLabel(progress)}</em>` : null}
        </div>
        <button className="primary-action" disabled=${isRunning} onClick=${onRun}>
          ${isRunning ? '运行中' : '运行回测'}
        </button>
      </div>
    </section>
  `;
}
