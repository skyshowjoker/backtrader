"""左侧控制面板 - 聚宽风格分析导航 + 策略配置"""

from dash import html, dcc

from ui.engines.data_fetcher import ETF_POOL


def create_sidebar():
    """创建左侧控制面板布局"""
    return html.Div([
        html.Div([
            _side_item('收益概述', '¥', active=True),
            _side_item('交易详情', '▤'),
            _side_item('每日持仓&收益', '▥'),
            _side_item('日志输出', '▦'),
            _side_item('性能分析', '◔'),
            html.Div(className='jq-side-separator'),
            _side_item('策略代码', '•'),
            _side_item('策略收益', '◌'),
            _side_item('基准收益', '◍'),
            _side_item('Alpha', '•'),
            _side_item('Beta', '•'),
            _side_item('Sharpe', '•'),
        ], className='jq-side-menu'),

        html.Div('策略配置', className='sidebar-title'),

        # ===== 策略选择 =====
        html.Div([
            html.Label('策略选择', className='sidebar-label'),
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
            html.Label('参数配置', className='sidebar-label'),
            html.Div(id='params-container', children=[
                html.Div('请先选择策略', className='sidebar-hint'),
            ]),
        ], className='sidebar-section'),

        # ===== 数据代码 =====
        html.Div([
            html.Label('标的代码', className='sidebar-label'),
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

        # ===== 策略上传 =====
        html.Div([
            html.Label('上传自定义策略', className='sidebar-label'),
            dcc.RadioItems(
                id='strategy-format',
                options=[
                    {'label': '自动识别', 'value': 'auto'},
                    {'label': 'Backtrader', 'value': 'backtrader'},
                    {'label': '聚宽', 'value': 'joinquant'},
                ],
                value='auto',
                inline=True,
                className='strategy-format-toggle',
                inputClassName='strategy-format-input',
                labelClassName='strategy-format-label',
            ),
            dcc.Upload(
                id='upload-strategy',
                children=html.Div([
                    '拖拽或 ',
                    html.A('点击上传 .py 文件', className='upload-link'),
                ]),
                className='upload-zone',
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


def _side_item(label, icon, active=False):
    """构建左侧分析导航项。"""
    class_name = 'jq-side-item jq-side-item-active' if active else 'jq-side-item'
    return html.Div([
        html.Span(icon, className='jq-side-icon'),
        html.Span(label, className='jq-side-label'),
    ], className=class_name)
