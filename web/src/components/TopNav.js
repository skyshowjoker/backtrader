import {html} from '../constants.js';

export default function TopNav() {
  return html`
    <header className="top-nav">
      <div className="brand">
        <span className="brand-bars"></span>
        <span className="brand-text">BackQuant</span>
      </div>
      <nav className="nav-links">
        <span>首页</span>
        <span className="active">量化研究平台</span>
        <span>策略社区</span>
        <span>帮助</span>
        <span>本地数据</span>
      </nav>
      <div className="avatar">BT</div>
    </header>
  `;
}
