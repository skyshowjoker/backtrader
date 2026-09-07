import {html} from '../constants.js';

export default function StrategyBar({strategyName, activeTab, setActiveTab}) {
  return html`
    <div className="strategy-bar">
      <h1 className="strategy-title">${strategyName || '未选择策略'}</h1>
      <div className="strategy-tabs">
        ${['回测', '归因分析', '交易记录', '日志'].map((tab) => html`
          <span
            key=${tab}
            className=${`tab ${activeTab === tab ? 'active' : ''}`}
            onClick=${() => setActiveTab(tab)}
          >${tab}</span>
        `)}
      </div>
    </div>
  `;
}
