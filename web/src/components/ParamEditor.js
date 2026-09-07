import {html} from '../constants.js';

export default function ParamEditor({schema, params, setParams}) {
  if (!schema.length) {
    return html`<div className="empty-line">无可配置参数</div>`;
  }

  function update(name, value) {
    setParams((current) => ({...current, [name]: value}));
  }

  return html`
    <div className="param-list">
      ${schema.map((param) => {
        if (param.type === 'bool') {
          return html`
            <label className="check-row" key=${param.name}>
              <input type="checkbox" checked=${Boolean(params[param.name])}
                onChange=${(e) => update(param.name, e.target.checked)} />
              <span>${param.label}</span>
            </label>
          `;
        }
        return html`
          <div className="param-row" key=${param.name}>
            <span>${param.label}</span>
            <input value=${params[param.name] ?? ''}
              inputMode=${param.type === 'str' ? 'text' : 'decimal'}
              onInput=${(e) => update(param.name, e.target.value)} />
          </div>
        `;
      })}
    </div>
  `;
}
