"""左侧控制面板 - 策略选择、参数配置、回测控制"""

import dash_bootstrap_components as dbc
from dash import html, dcc

from ui.engines.data_fetcher import BENCHMARK_POOL, ETF_POOL


def create_sidebar():
    """创建左侧控制面板布局"""
    return html.Div([
        # ===== 策略选择 =====
        html.Div([
            html.Label('📊 策略选择', className='sidebar-label'),
            dcc.Dropdown(
                id='strategy-selector',
                options=[],  # 由回调动态填充
                value=None,
                placeholder='请选择策略...',
                className='sidebar-dropdown',
            ),
        ], className='sidebar-section'),

        # ===== 参数配置 =====
        html.Div([
            html.Label('⚙️ 参数配置', className='sidebar-label'),
            html.Div(id='params-container', children=[
                html.Div('请先选择策略', className='sidebar-hint'),
            ]),
        ], className='sidebar-section'),

        # ===== 日期范围 =====
        html.Div([
            html.Label('📅 日期范围', className='sidebar-label'),
            dcc.DatePickerRange(
                id='date-range',
                start_date='2020-01-01',
                end_date='2025-12-31',
                display_format='YYYY-MM-DD',
                className='sidebar-datepicker',
            ),
        ], className='sidebar-section'),

        # ===== 资金设置 =====
        html.Div([
            html.Label('💰 初始资金', className='sidebar-label'),
            dcc.Input(
                id='initial-cash',
                type='number',
                value=1000000,
                placeholder='初始资金',
                className='sidebar-input',
            ),
        ], className='sidebar-section'),

        html.Div([
            html.Label('💸 佣金率', className='sidebar-label'),
            dcc.Input(
                id='commission',
                type='number',
                value=0.0002,
                step=0.0001,
                placeholder='佣金率',
                className='sidebar-input',
            ),
        ], className='sidebar-section'),

        # ===== 基准选择 =====
        html.Div([
            html.Label('📈 基准指数', className='sidebar-label'),
            dcc.Dropdown(
                id='benchmark-selector',
                options=[{'label': f"{code} {name}", 'value': code}
                         for code, name in BENCHMARK_POOL.items()],
                value='000300',
                placeholder='选择基准...',
                className='sidebar-dropdown',
            ),
        ], className='sidebar-section'),

        # ===== 数据代码 =====
        html.Div([
            html.Label('🔗 标的代码', className='sidebar-label'),
            dcc.Dropdown(
                id='data-codes',
                options=[{'label': f"{code} {name}", 'value': code}
                         for code, name in ETF_POOL.items()],
                value=['510300'],
                multi=True,
                placeholder='选择标的（可多选）...',
                className='sidebar-dropdown',
            ),
        ], className='sidebar-section'),

        # ===== 运行按钮 =====
        html.Div([
            dbc.Button(
                '🚀 运行回测',
                id='run-button',
                color='primary',
                className='sidebar-run-btn',
                style={'width': '100%', 'fontWeight': 'bold', 'fontSize': '16px'},
            ),
        ], className='sidebar-section'),

        # ===== 状态消息 =====
        html.Div(id='status-message', className='sidebar-status'),

        # ===== 策略上传 =====
        html.Div([
            html.Label('📤 上传自定义策略', className='sidebar-label'),
            dcc.Upload(
                id='upload-strategy',
                children=html.Div([
                    '拖拽或 ',
                    html.A('点击上传 .py 文件', className='upload-link'),
                ]),
                style={
                    'width': '100%',
                    'height': '60px',
                    'lineHeight': '60px',
                    'borderWidth': '1px',
                    'borderStyle': 'dashed',
                    'borderRadius': '5px',
                    'textAlign': 'center',
                    'margin': '10px 0',
                    'color': '#666',
                },
                multiple=False,
                accept='.py',
            ),
            html.Div(id='upload-status', className='upload-status'),
        ], className='sidebar-section'),

        # ===== 隐藏组件 =====
        dcc.Store(id='task-id-store'),
        dcc.Store(id='params-store'),  # 策略参数缓存
        dcc.Interval(
            id='interval-component',
            interval=2000,  # 2秒轮询
            n_intervals=0,
            disabled=True,  # 默认禁用
        ),
        dcc.Store(id='backtest-results'),

    ], className='sidebar')
