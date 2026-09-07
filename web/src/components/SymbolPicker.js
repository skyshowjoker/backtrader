import {html} from '../constants.js';

export default function SymbolPicker({etfs, selected, setSelected}) {
  function toggle(code) {
    setSelected((current) => {
      if (current.includes(code)) return current.filter((item) => item !== code);
      return [...current, code];
    });
  }

  return html`
    <div className="symbol-picker">
      <div className="symbol-toolbar">
        <span>${selected.length}/${etfs.length}</span>
        <div className="symbol-actions">
          <button type="button" onClick=${() => setSelected(etfs.map((item) => item.code))}>全选</button>
          <button type="button" onClick=${() => setSelected([])}>清空</button>
        </div>
      </div>
      <div className="symbol-grid">
        ${etfs.map((item) => html`
          <button key=${item.code} type="button"
            className=${selected.includes(item.code) ? 'symbol selected' : 'symbol'}
            onClick=${() => toggle(item.code)}>
            <span>${item.code}</span>
            <b>${item.name}</b>
          </button>
        `)}
      </div>
    </div>
  `;
}
