import {html} from '../constants.js';
import {taskStatus} from '../utils/formatters.js';

export default function TaskTable({tasks, openTask}) {
  return html`
    <div className="task-table-wrap">
      <table>
        <thead><tr>
          ${['ID','状态','策略','标的','区间','收益','更新时间','操作'].map(l => html`<th key=${l}>${l}</th>`)}
        </tr></thead>
        <tbody>
          ${(tasks || []).length === 0 ? html`<tr><td colspan="8" className="empty">暂无回测记录</td></tr>` :
            tasks.map((t) => html`
              <tr key=${t.task_id}>
                <td>${t.task_id}</td>
                <td>${taskStatus(t.status)}</td>
                <td>${t.strategy || '--'}</td>
                <td>${(t.config?.data_codes || []).join(', ')}</td>
                <td>${t.config?.start_date || '--'} - ${t.config?.end_date || '--'}</td>
                <td className=${(+t.summary?.total_return||0)>=0?'positive':'negative'}>${t.summary?.total_return != null ? (+t.summary.total_return).toFixed(2)+'%' : '--'}</td>
                <td>${t.updated_at || t.created_at || '--'}</td>
                <td>
                  <button className="action-btn" disabled=${!['done','error'].includes(t.status)}
                    onClick=${() => openTask(t.task_id)}>载入</button>
                </td>
              </tr>
            `)
          }
        </tbody>
      </table>
    </div>
  `;
}
