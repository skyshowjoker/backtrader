import {html} from '../constants.js';
import {fixed, formatDirection, tradeStatus, orderStatusText} from '../utils/formatters.js';

export default function TradesPanel({result}) {
  const trades = result?.trades || [];
  const positions = result?.positions || [];
  const orders = result?.orders || [];

  return html`
    <div className="trades-panel">
      <h2>交易记录</h2>
      <table>
        <thead><tr>
          ${['标的','方向','入场','出场','入价','出价','数量','盈亏','天数'].map(l => html`<th key=${l}>${l}</th>`)}
        </tr></thead>
        <tbody>
          ${trades.length === 0 ? html`<tr><td colspan="9" className="empty">暂无记录</td></tr>` :
            trades.map((t, i) => html`
              <tr key=${i}>
                <td>${t.data_name || '--'}</td>
                <td>${formatDirection(t.direction)}</td>
                <td>${t.entry_date || '--'}</td>
                <td>${t.exit_date || '持仓中'}</td>
                <td>${fixed(t.entry_price, 3)}</td>
                <td>${fixed(t.exit_price ?? t.last_price, 3)}</td>
                <td>${fixed(t.size, 0)}</td>
                <td className=${(+t.net_pnl||0)>=0?'positive':'negative'}>${fixed(t.net_pnl, 2)}</td>
                <td>${t.duration ?? '--'}</td>
              </tr>
            `)
          }
        </tbody>
      </table>

      <h2 style="margin-top:24px">订单流水</h2>
      <table>
        <thead><tr>
          ${['日期','标的','方向','状态','数量','价格','佣金'].map(l => html`<th key=${l}>${l}</th>`)}
        </tr></thead>
        <tbody>
          ${orders.length === 0 ? html`<tr><td colspan="7" className="empty">暂无订单</td></tr>` :
            orders.map((o) => html`
              <tr key=${o.ref}>
                <td>${o.date || '--'}</td>
                <td>${o.data_name || '--'}</td>
                <td>${formatDirection(o.type)}</td>
                <td>${orderStatusText(o.status)}</td>
                <td>${fixed(o.executed_size, 0)}</td>
                <td>${fixed(o.executed_price, 3)}</td>
                <td>${fixed(o.commission, 2)}</td>
              </tr>
            `)
          }
        </tbody>
      </table>
    </div>
  `;
}
