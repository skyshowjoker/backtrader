"""图表区 - 净值曲线 + 基准曲线 + 标的价格 + 买卖信号"""

from dash import html, dcc
import plotly.graph_objects as go


def create_chart_tab():
    """创建图表 Tab 布局"""
    return html.Div([
        # 图表切换控件
        html.Div([
            dcc.Checklist(
                id='chart-toggles',
                options=[
                    {'label': '📈 策略净值', 'value': 'strategy_nav'},
                    {'label': '📊 基准净值', 'value': 'benchmark_nav'},
                    {'label': '📉 标的价格', 'value': 'underlying_price'},
                    {'label': '🔺 买卖信号', 'value': 'signals'},
                ],
                value=['strategy_nav', 'benchmark_nav', 'signals'],
                inline=True,
                className='chart-toggles',
                inputStyle={'margin-right': '5px'},
                labelStyle={'margin-right': '15px', 'cursor': 'pointer'},
            ),
        ], className='chart-controls'),

        # 主图表
        dcc.Loading(
            id='chart-loading',
            type='circle',
            children=dcc.Graph(
                id='nav-chart',
                config={
                    'displayModeBar': True,
                    'scrollZoom': True,
                    'displaylogo': False,
                    'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                },
                style={'height': '65vh'},
            ),
        ),

        # 空状态提示
        html.Div(id='chart-placeholder', children=[
            html.Div([
                html.I(className='fas fa-chart-line', style={'fontSize': '48px', 'color': '#ccc'}),
                html.P('选择策略并点击"运行回测"查看图表', style={'color': '#999', 'marginTop': '15px'}),
            ], className='chart-placeholder-content'),
        ]),
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
        toggles = ['strategy_nav', 'benchmark_nav', 'signals']

    fig = go.Figure()

    has_data = False

    # 1. 策略净值曲线
    if 'strategy_nav' in toggles and result.get('nav_dates'):
        fig.add_trace(go.Scatter(
            x=result['nav_dates'],
            y=result['nav_values'],
            name='策略净值',
            line=dict(color='#2563eb', width=2),
            hovertemplate='日期: %{x}<br>净值: %{y:.4f}<extra></extra>',
        ))
        has_data = True

    # 2. 基准净值曲线
    if 'benchmark_nav' in toggles and result.get('benchmark_dates'):
        fig.add_trace(go.Scatter(
            x=result['benchmark_dates'],
            y=result['benchmark_values'],
            name='基准净值',
            line=dict(color='#94a3b8', width=1.5, dash='dash'),
            hovertemplate='日期: %{x}<br>净值: %{y:.4f}<extra></extra>',
        ))
        has_data = True

    # 3. 标的价格曲线（右轴）
    if 'underlying_price' in toggles and result.get('underlying_dates'):
        fig.add_trace(go.Scatter(
            x=result['underlying_dates'],
            y=result['underlying_prices'],
            name=f"标的价格 ({result.get('underlying_name', '')})",
            line=dict(color='#f59e0b', width=1),
            yaxis='y2',
            opacity=0.7,
            hovertemplate='日期: %{x}<br>价格: %{y:.3f}<extra></extra>',
        ))
        has_data = True

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
                    size=12,
                    color='#22c55e',
                    line=dict(width=1, color='#15803d'),
                ),
                hovertemplate='买入<br>日期: %{x}<br>价格: %{text}<extra></extra>',
                text=[f"{s['price']:.3f}" for s in buy_signals],
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
                    size=12,
                    color='#ef4444',
                    line=dict(width=1, color='#b91c1c'),
                ),
                hovertemplate='卖出<br>日期: %{x}<br>价格: %{text}<extra></extra>',
                text=[f"{s['price']:.3f}" for s in sell_signals],
            ))

        has_data = True

    # 布局设置
    fig.update_layout(
        template='plotly_white',
        hovermode='x unified',
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1,
        ),
        margin=dict(l=60, r=60, t=40, b=40),
        xaxis=dict(
            title='日期',
            gridcolor='#f0f0f0',
        ),
        yaxis=dict(
            title='净值',
            gridcolor='#f0f0f0',
            tickformat='.2f',
        ),
    )

    # 如果有标的价格，添加右轴
    if 'underlying_price' in toggles and result.get('underlying_dates'):
        fig.update_layout(
            yaxis2=dict(
                title='价格',
                overlaying='y',
                side='right',
                tickformat='.2f',
                showgrid=False,
            )
        )

    if not has_data:
        fig.add_annotation(
            text="暂无数据，请运行回测",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=16, color='#999'),
        )

    return fig


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
