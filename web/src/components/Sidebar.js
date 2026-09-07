import {html} from '../constants.js';

export default function Sidebar({
  strategies, selectedStrategy, strategyName, setStrategyName,
  params, setParams, etfs, dataCodes, setDataCodes,
  strategyFormat, setStrategyFormat, onUpload,
}) {
  return html`
    <aside className="side-panel">
      <div className="side-form">
        <h2>策略配置</h2>
        <label>策略选择</label>
        <select value=${strategyName} onInput=${(e) => setStrategyName(e.target.value)}>
          ${(strategies || []).map((item) => html`
            <option key=${item.name} value=${item.name}>
              ${item.category === 'custom' ? '自定义 · ' : ''}${item.name}
            </option>
          `)}
        </select>

        <label>参数配置</label>
        <${ParamEditor} schema=${selectedStrategy?.params || []} params=${params} setParams=${setParams} />

        <label>标的代码</label>
        <${SymbolPicker} etfs=${etfs} selected=${dataCodes} setSelected=${setDataCodes} />

        <label>上传自定义策略</label>
        <div className="segment">
          ${[['auto', '自动'], ['backtrader', 'BT'], ['joinquant', '聚宽']].map(([v, l]) => html`
            <button key=${v} type="button"
              className=${strategyFormat === v ? 'selected' : ''}
              onClick=${() => setStrategyFormat(v)}>${l}</button>
          `)}
        </div>
        <label className="upload-box">
          <input type="file" accept=".py" onChange=${onUpload} />
          <span>点击上传 .py 文件</span>
        </label>
      </div>
    </aside>
  `;
}

import ParamEditor from './ParamEditor.js';
import SymbolPicker from './SymbolPicker.js';
