import {html} from '../constants.js';
import {logLevelText} from '../utils/formatters.js';

export default function LogsPanel({result}) {
  const logs = result?.logs || [];

  return html`
    <div className="logs-panel">
      <h2>策略日志</h2>
      <div className="log-list">
        ${logs.length === 0 ? html`<div className="empty">暂无日志</div>` :
          logs.map((entry, i) => html`
            <div key=${i} className=${`log-entry ${entry.level}`}>
              <span className="log-date">${entry.date || ''}</span>
              <span className="log-level">${logLevelText(entry.level)}</span>
              <span className="log-message">${entry.message}</span>
            </div>
          `)
        }
      </div>
    </div>
  `;
}
