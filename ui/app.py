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
from ui.engines.data_fetcher import BENCHMARK_POOL

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

# 注册本地 strategies/etf/etf.py 聚宽策略（只读取并适配，不改动策略源码）
try:
    from ui.strategies.joinquant_builtin import register_joinquant_etf_strategy
    register_joinquant_etf_strategy()
except Exception:
    pass

# ===== 创建 Dash 应用 =====
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    title='Backtrader 回测工作台',
)

server = app.server  # Gunicorn 部署用

# ===== 应用布局 =====
app.layout = dbc.Container([
    # 聚宽风格顶部导航
    html.Div([
        html.Div([
            html.Div([
                html.Span(className='jq-logo-bars'),
                html.Span('BackQuant', className='jq-logo-text'),
            ], className='jq-brand'),
            html.Div([
                html.Span('首页'),
                html.Span('量化研究平台', className='jq-nav-active'),
                html.Span('策略社区'),
                html.Span('帮助'),
                html.Span('本地数据'),
            ], className='jq-nav'),
        ], className='jq-header-inner'),
        html.Div([
            html.Div('BT', className='jq-avatar'),
        ], className='jq-user-zone'),
    ], className='app-header'),

    # 策略标题和工作区导航
    html.Div([
        html.Div([
            html.Span('‹', className='strategy-back'),
            html.H1('ETF轮动最终优化', className='strategy-title'),
            html.Span('✎', className='strategy-edit-icon'),
        ], className='strategy-title-group'),
        html.Div([
            html.Span('编辑策略', className='worktab worktab-active'),
            html.Span('回测详情', className='worktab'),
            html.Span('编译运行列表', className='worktab'),
            html.Span('回测列表', className='worktab'),
        ], className='workspace-tabs'),
    ], className='strategy-titlebar'),

    # 回测参数工具条
    html.Div([
        html.Div([
            html.Span('设置：', className='toolbar-label'),
            dcc.DatePickerRange(
                id='date-range',
                start_date='2020-01-01',
                end_date='2025-12-31',
                display_format='YYYY-MM-DD',
                clearable=False,
                className='toolbar-datepicker',
            ),
            html.Span('¥', className='toolbar-currency'),
            dcc.Input(
                id='initial-cash',
                type='text',
                value='1000000',
                placeholder='初始资金',
                className='toolbar-input cash-input',
            ),
            dcc.Input(
                id='commission',
                type='text',
                value='0.0002',
                placeholder='佣金率',
                className='toolbar-input commission-input',
            ),
            dcc.Dropdown(
                id='benchmark-selector',
                options=[{'label': f"{code} {name}", 'value': code}
                         for code, name in BENCHMARK_POOL.items()],
                value='000300',
                clearable=False,
                className='toolbar-dropdown benchmark-toolbar',
            ),
            dcc.Dropdown(
                id='frequency-selector',
                options=[
                    {'label': '每天', 'value': 'daily'},
                    {'label': '每周', 'value': 'weekly'},
                    {'label': '每月', 'value': 'monthly'},
                ],
                value='daily',
                clearable=False,
                className='toolbar-dropdown frequency-toolbar',
            ),
            html.Span('Python3', className='python-badge'),
        ], className='backtest-settings'),
        html.Div([
            html.Div(id='status-message', className='toolbar-status'),
            dbc.Button('运行回测', id='run-button', color='primary',
                       className='toolbar-run-btn'),
        ], className='toolbar-actions'),
    ], className='backtest-toolbar'),

    # 主体区域
    html.Div([
        # 左侧控制面板
        create_sidebar(),

        # 右侧内容区
        html.Div([
            dcc.Tabs(id='main-tabs', value='chart', children=[
                dcc.Tab(label='收益概览', value='chart', className='custom-tab',
                        selected_className='custom-tab--selected'),
                dcc.Tab(label='归因分析', value='metrics', className='custom-tab',
                        selected_className='custom-tab--selected'),
                dcc.Tab(label='交易详情', value='trades', className='custom-tab',
                        selected_className='custom-tab--selected'),
            ], className='custom-tabs'),

            # Tab 内容
            html.Div(id='tab-content', className='main-tab-content'),
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
