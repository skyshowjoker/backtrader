"""Backtrader 可视化回测平台 - 应用入口

启动方式:
    python -m ui.app
    或
    python ui/app.py

访问: http://127.0.0.1:8050
"""

import sys
import os

# 确保项目根目录在 sys.path 中
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import dash
from dash import html, dcc, Input, Output
import dash_bootstrap_components as dbc

# 注册内置策略（导入即注册）
from ui.strategies.sma_cross import SMACrossStrategy
from ui.strategies.registry import StrategyRegistry

# 导入布局组件
from ui.layouts.sidebar import create_sidebar
from ui.layouts.chart_tab import create_chart_tab
from ui.layouts.metrics_tab import create_metrics_tab
from ui.layouts.trades_tab import create_trades_tab

# 导入回调注册
from ui.callbacks.backtest_callbacks import register_backtest_callbacks
from ui.callbacks.strategy_callbacks import register_strategy_callbacks
from ui.callbacks.upload_callbacks import register_upload_callbacks

# ===== 注册内置策略 =====
StrategyRegistry.register(
    name='SMA双均线交叉',
    strategy_class=SMACrossStrategy,
    description='短期均线上穿长期均线买入，下穿卖出',
    category='builtin',
)

# 尝试注册 ETF 轮动策略（可能因 akshare 依赖失败）
try:
    from ui.strategies.etf_rotate import register_etf_strategy
    register_etf_strategy()
except Exception:
    pass

# ===== 创建 Dash 应用 =====
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY],
    suppress_callback_exceptions=True,
    title='Backtrader 可视化回测平台',
)

server = app.server  # Gunicorn 部署用

# ===== 应用布局 =====
app.layout = dbc.Container([
    # 顶部标题栏
    html.Div([
        html.Div([
            html.H1('📈 Backtrader 可视化回测平台', className='app-title'),
            html.Span('交互式策略回测 · 净值曲线 · 信号分析 · 绩效评估', className='app-subtitle'),
        ], className='header-content'),
    ], className='app-header'),

    # 主体区域
    html.Div([
        # 左侧控制面板
        create_sidebar(),

        # 右侧内容区
        html.Div([
            dcc.Tabs(id='main-tabs', value='chart', children=[
                dcc.Tab(label='📊 图表', value='chart', className='custom-tab',
                        selected_className='custom-tab--selected'),
                dcc.Tab(label='📋 绩效指标', value='metrics', className='custom-tab',
                        selected_className='custom-tab--selected'),
                dcc.Tab(label='📝 交易记录', value='trades', className='custom-tab',
                        selected_className='custom-tab--selected'),
            ], className='custom-tabs'),

            # Tab 内容
            html.Div(id='tab-content', className='tab-content'),
        ], className='main-content'),
    ], className='app-body'),

], fluid=True, className='app-container')


# ===== Tab 切换回调 =====
@app.callback(
    Output('tab-content', 'children'),
    [Input('main-tabs', 'value')],
)
def render_tab(tab_value):
    if tab_value == 'chart':
        return create_chart_tab()
    elif tab_value == 'metrics':
        return create_metrics_tab()
    elif tab_value == 'trades':
        return create_trades_tab()
    return create_chart_tab()


# ===== 注册回调 =====
register_backtest_callbacks(app)
register_strategy_callbacks(app)
register_upload_callbacks(app)

# ===== 初始化策略下拉选项 =====
# 在应用启动时设置初始选项
app.layout.children.append(
    dcc.Store(id='init-store', data=StrategyRegistry.get_dropdown_options())
)


# ===== 启动 =====
if __name__ == '__main__':
    print("\n🚀 Backtrader 可视化回测平台启动中...")
    print("📍 访问地址: http://127.0.0.1:8050\n")
    app.run(debug=True, host='127.0.0.1', port=8050)
