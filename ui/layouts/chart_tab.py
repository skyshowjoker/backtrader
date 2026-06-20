"""图表区 - 多曲线收益对比 + 标的走势 + 策略信号分析"""

from dash import html, dcc
import plotly.graph_objects as go

_SERIES_COLORS = [
    '#2f6bff', '#00a896', '#c8a24a', '#8b5cf6', '#ef7d36',
    '#2aa7a5', '#6a8caf', '#b45f3d', '#5568fe', '#0b7285',
]


def create_chart_tab():
    """创建图表 Tab 布局"""
    return html.Div([
        html.Div([
            html.Div([
                html.H3('多维收益对比', className='panel-title'),
                html.Span('策略、基准、超额收益、多标的价格与收益同视图分析', className='panel-subtitle'),
            ], className='panel-heading'),
            dcc.Checklist(
                id='chart-toggles',
                options=[
                    {'label': '策略净值', 'value': 'strategy_nav'},
                    {'label': '策略收益', 'value': 'strategy_return'},
                    {'label': '基准收益', 'value': 'benchmark_return'},
                    {'label': '超额收益', 'value': 'excess_return'},
                    {'label': '标的价格', 'value': 'underlying_price'},
                    {'label': '标的收益', 'value': 'underlying_return'},
                    {'label': '买卖信号', 'value': 'signals'},
                ],
                value=['strategy_nav', 'strategy_return', 'benchmark_return',
                       'excess_return', 'signals'],
                inline=True,
                className='chart-toggles',
                inputClassName='chart-toggle-input',
                labelClassName='chart-toggle-label',
            ),
        ], className='chart-toolbar'),

        # 主图表
        dcc.Loading(
            id='chart-loading',
            type='circle',
            children=dcc.Graph(
                id='nav-chart',
                figure=build_chart_figure({}),
                config={
                    'displayModeBar': True,
                    'scrollZoom': True,
                    'displaylogo': False,
                    'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                },
                className='main-graph',
            ),
        ),

        html.Div([
            html.Div([
                html.H3('策略信号分析', className='panel-title'),
                html.Span('买卖信号频率、方向和标的分布', className='panel-subtitle'),
            ], className='panel-heading signal-heading'),
            html.Div(id='signal-summary-content',
                     children=build_signal_summary({}),
                     className='signal-summary-grid'),
            dcc.Graph(
                id='signal-analysis-chart',
                figure=build_signal_analysis_figure({}),
                config={'displayModeBar': False},
                className='signal-graph',
            ),
        ], className='signal-analysis-panel'),

        # 保留给回调兼容；空状态由 Plotly 图表自身承载
        html.Div(id='chart-placeholder', style={'display': 'none'}),
    ], className='chart-tab')


def build_chart_figure(result, toggles=None):
    """构建 Plotly 图表

    Args:
        result: dict, result_extractor 返回的结果
        toggles: list[str], 显示的曲线列表

    Returns:
        plotly.graph_objects.Figure
    """
    if toggles is None:
        toggles = ['strategy_nav', 'strategy_return', 'benchmark_return',
                   'excess_return', 'signals']

    fig = go.Figure()

    has_data = False

    # 1. 策略净值曲线
    if 'strategy_nav' in toggles and result.get('nav_dates'):
        _add_line(
            fig,
            result['nav_dates'],
            result['nav_values'],
            '策略净值',
            '#2f6bff',
            '净值: %{y:.4f}',
            width=2.6,
        )
        has_data = True

    # 2. 策略、基准、超额收益曲线（右轴）
    if 'strategy_return' in toggles and result.get('strategy_return_dates'):
        _add_line(
            fig,
            result['strategy_return_dates'],
            result['strategy_return_values'],
            '策略收益',
            '#00a896',
            '收益: %{y:.2f}%',
            yaxis='y2',
            width=2.2,
        )
        has_data = True

    if 'benchmark_return' in toggles and result.get('benchmark_return_dates'):
        _add_line(
            fig,
            result['benchmark_return_dates'],
            result['benchmark_return_values'],
            _benchmark_label(result),
            '#6a8caf',
            '收益: %{y:.2f}%',
            yaxis='y2',
            dash='dash',
            width=2.0,
        )
        has_data = True

    if 'excess_return' in toggles and result.get('excess_return_dates'):
        _add_line(
            fig,
            result['excess_return_dates'],
            result['excess_return_values'],
            '超额收益',
            '#c8a24a',
            '超额: %{y:.2f}%',
            yaxis='y2',
            width=2.2,
        )
        has_data = True

    # 3. 多标的曲线
    underlying_series = result.get('underlying_series') or []
    if 'underlying_price' in toggles:
        for index, series in enumerate(underlying_series):
            color = _SERIES_COLORS[index % len(_SERIES_COLORS)]
            _add_line(
                fig,
                series.get('dates', []),
                series.get('normalized', []),
                f"{series.get('name', '')} 价格归一",
                color,
                '归一价格: %{y:.4f}',
                dash='dot',
                width=1.55,
                opacity=0.78,
            )
            has_data = has_data or bool(series.get('dates'))

    if 'underlying_return' in toggles:
        for index, series in enumerate(underlying_series):
            color = _SERIES_COLORS[index % len(_SERIES_COLORS)]
            _add_line(
                fig,
                series.get('dates', []),
                series.get('returns', []),
                f"{series.get('name', '')} 收益",
                color,
                '收益: %{y:.2f}%',
                yaxis='y2',
                dash='longdash',
                width=1.5,
                opacity=0.72,
            )
            has_data = has_data or bool(series.get('dates'))

    # 4. 买卖信号
    if 'signals' in toggles and result.get('signals'):
        buy_signals = [s for s in result['signals'] if s['type'] == 'buy']
        sell_signals = [s for s in result['signals'] if s['type'] == 'sell']

        if buy_signals:
            # 买入信号映射到策略净值轴
            buy_nav = _map_signal_to_nav(buy_signals, result)
            fig.add_trace(go.Scatter(
                x=[s['date'] for s in buy_signals],
                y=buy_nav if buy_nav else [s['price'] for s in buy_signals],
                name='买入信号',
                mode='markers',
                marker=dict(
                    symbol='triangle-up',
                    size=11,
                    color='#00a896',
                    line=dict(width=1.5, color='#ffffff'),
                ),
                hovertemplate='买入<br>日期: %{x}<br>标的: %{customdata}<br>价格: %{text}<extra></extra>',
                text=[f"{s['price']:.3f}" for s in buy_signals],
                customdata=[s.get('data_name', '') for s in buy_signals],
            ))

        if sell_signals:
            sell_nav = _map_signal_to_nav(sell_signals, result)
            fig.add_trace(go.Scatter(
                x=[s['date'] for s in sell_signals],
                y=sell_nav if sell_nav else [s['price'] for s in sell_signals],
                name='卖出信号',
                mode='markers',
                marker=dict(
                    symbol='triangle-down',
                    size=11,
                    color='#b45f3d',
                    line=dict(width=1.5, color='#ffffff'),
                ),
                hovertemplate='卖出<br>日期: %{x}<br>标的: %{customdata}<br>价格: %{text}<extra></extra>',
                text=[f"{s['price']:.3f}" for s in sell_signals],
                customdata=[s.get('data_name', '') for s in sell_signals],
            ))

        has_data = True

    # 布局设置
    fig.update_layout(
        template='plotly_white',
        paper_bgcolor='#fbfcfe',
        plot_bgcolor='#fbfcfe',
        hovermode='x unified',
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.04,
            xanchor='right',
            x=1,
            bgcolor='rgba(251,252,254,0.88)',
            font=dict(size=12, color='#243447'),
        ),
        margin=dict(l=56, r=56, t=34, b=42),
        xaxis=dict(
            title='日期',
            gridcolor='#e8edf3',
            linecolor='#ccd6e3',
            zeroline=False,
        ),
        yaxis=dict(
            title='净值 / 归一价格',
            gridcolor='#e8edf3',
            linecolor='#ccd6e3',
            tickformat='.2f',
            zeroline=False,
        ),
        yaxis2=dict(
            title='累计收益 / 超额收益 (%)',
            overlaying='y',
            side='right',
            tickformat='.1f',
            showgrid=False,
            linecolor='#ccd6e3',
            zeroline=False,
        ),
    )

    if not has_data:
        fig.add_annotation(
            text="暂无回测数据，运行后将实时加载曲线",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=16, color='#8796a8'),
        )

    return fig


def build_signal_analysis_figure(result):
    """构建策略信号分析图。"""
    analysis = result.get('signal_analysis') or {}
    timeline = analysis.get('timeline') or []

    fig = go.Figure()

    if timeline:
        dates = [item['date'] for item in timeline]
        fig.add_trace(go.Bar(
            x=dates,
            y=[item['buy'] for item in timeline],
            name='买入信号',
            marker_color='#00a896',
            hovertemplate='日期: %{x}<br>买入: %{y}<extra></extra>',
        ))
        fig.add_trace(go.Bar(
            x=dates,
            y=[-item['sell'] for item in timeline],
            name='卖出信号',
            marker_color='#b45f3d',
            hovertemplate='日期: %{x}<br>卖出: %{customdata}<extra></extra>',
            customdata=[item['sell'] for item in timeline],
        ))
        fig.add_trace(go.Scatter(
            x=dates,
            y=[item['exposure'] for item in timeline],
            name='净信号累积',
            yaxis='y2',
            mode='lines+markers',
            line=dict(color='#c8a24a', width=2),
            marker=dict(size=6),
            hovertemplate='日期: %{x}<br>净信号累积: %{y}<extra></extra>',
        ))
    else:
        fig.add_annotation(
            text='暂无信号数据',
            xref='paper',
            yref='paper',
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=14, color='#8796a8'),
        )

    fig.update_layout(
        template='plotly_white',
        paper_bgcolor='#fbfcfe',
        plot_bgcolor='#fbfcfe',
        barmode='relative',
        height=260,
        margin=dict(l=48, r=48, t=16, b=34),
        legend=dict(orientation='h', y=1.08, x=1, xanchor='right'),
        xaxis=dict(gridcolor='#e8edf3', zeroline=False),
        yaxis=dict(title='信号次数', gridcolor='#e8edf3', zeroline=False),
        yaxis2=dict(title='净信号', overlaying='y', side='right',
                    showgrid=False, zeroline=False),
    )

    return fig


def build_signal_summary(result):
    """构建信号摘要卡片。"""
    analysis = result.get('signal_analysis') or {}
    symbols = analysis.get('symbols') or []
    active_symbols = sum(1 for item in symbols if item.get('buy') or item.get('sell'))

    items = [
        ('全部信号', analysis.get('total', 0), '#2f6bff'),
        ('买入', analysis.get('buy', 0), '#00a896'),
        ('卖出', analysis.get('sell', 0), '#b45f3d'),
        ('覆盖标的', active_symbols, '#c8a24a'),
    ]

    return [
        html.Div([
            html.Div(label, className='signal-summary-label'),
            html.Div(value, className='signal-summary-value', style={'color': color}),
        ], className='signal-summary-card')
        for label, value, color in items
    ]


def _add_line(fig, x, y, name, color, hover_value, yaxis='y',
              width=2.0, dash=None, opacity=1.0):
    """添加统一风格折线。"""
    if not x or not y:
        return

    fig.add_trace(go.Scatter(
        x=x,
        y=y,
        name=name,
        mode='lines',
        yaxis=yaxis,
        opacity=opacity,
        line=dict(color=color, width=width, dash=dash),
        hovertemplate='日期: %{x}<br>' + hover_value + '<extra></extra>',
    ))


def _benchmark_label(result):
    """生成基准图例名称。"""
    source = result.get('benchmark_source') or ''
    if source.startswith('proxy:'):
        return f"基准收益 ({source.split(':', 1)[1]}代用)"
    return '基准收益'


def _map_signal_to_nav(signals, result):
    """将买卖信号映射到策略净值轴上

    根据信号日期查找对应的策略净值，使信号标记在净值曲线上。
    """
    if not result.get('nav_dates') or not result.get('nav_values'):
        return []

    nav_dict = dict(zip(result['nav_dates'], result['nav_values']))
    mapped = []
    for s in signals:
        nav_val = nav_dict.get(s['date'])
        mapped.append(nav_val if nav_val is not None else None)

    # 如果全部为 None，返回空列表（使用价格轴代替）
    if all(v is None for v in mapped):
        return []

    return mapped
