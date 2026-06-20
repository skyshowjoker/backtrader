"""绩效指标 Tab - 关键指标卡片 + 回撤曲线"""

from dash import html, dcc
import plotly.graph_objects as go


def create_metrics_tab():
    """创建绩效指标 Tab 布局"""
    return html.Div([
        html.Div([
            html.H3('绩效概览', className='panel-title'),
            html.Span('收益、风险与交易质量', className='panel-subtitle'),
        ], className='panel-heading metrics-heading'),

        # 指标卡片网格
        html.Div(id='metrics-container', children=[
            _metric_card('总收益率', 'total_return', '%', '#2f6bff'),
            _metric_card('年化收益率', 'annual_return', '%', '#00a896'),
            _metric_card('夏普比率', 'sharpe_ratio', '', '#0b7285'),
            _metric_card('最大回撤', 'max_drawdown', '%', '#b45f3d'),
            _metric_card('胜率', 'win_rate', '%', '#c8a24a'),
            _metric_card('盈亏比', 'profit_factor', '', '#2aa7a5'),
            _metric_card('总交易次数', 'total_trades', '次', '#5b6b7d'),
            _metric_card('最大回撤持续', 'max_drawdown_duration', '天', '#8b5cf6'),
        ], className='metrics-grid'),

        # 回撤曲线
        html.Div([
            html.H5('回撤曲线', className='section-title'),
            dcc.Graph(
                id='drawdown-chart',
                config={'displayModeBar': False},
                className='drawdown-graph',
            ),
        ], className='metrics-drawdown-section'),

    ], className='metrics-tab')


def build_metrics_content(metrics):
    """构建绩效指标内容

    Args:
        metrics: dict, result_extractor 返回的 metrics 字典

    Returns:
        list[html.Div], 指标卡片列表
    """
    cards = []

    card_configs = [
        ('总收益率', 'total_return', '%', '#2f6bff', _fmt_pct),
        ('年化收益率', 'annual_return', '%', '#00a896', _fmt_pct),
        ('夏普比率', 'sharpe_ratio', '', '#0b7285', _fmt_sharpe),
        ('最大回撤', 'max_drawdown', '%', '#b45f3d', _fmt_pct),
        ('胜率', 'win_rate', '%', '#c8a24a', _fmt_pct),
        ('盈亏比', 'profit_factor', '', '#2aa7a5', _fmt_pf),
        ('总交易次数', 'total_trades', '次', '#5b6b7d', _fmt_int),
        ('最大回撤持续', 'max_drawdown_duration', '天', '#8b5cf6', _fmt_int),
    ]

    for label, key, unit, color, fmt_func in card_configs:
        value = metrics.get(key)
        display_value = fmt_func(value, unit)
        cards.append(_build_metric_card(label, display_value, color))

    return cards


def build_drawdown_chart(result):
    """构建回撤曲线图

    从策略净值计算回撤序列。
    """
    nav_values = result.get('nav_values', [])
    nav_dates = result.get('nav_dates', [])

    if not nav_values or not nav_dates:
        fig = go.Figure()
        fig.add_annotation(text="暂无数据", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, font=dict(size=14, color='#94a3b8'))
        fig.update_layout(template='plotly_white', height=280, margin=dict(l=54, r=24, t=20, b=34))
        return fig

    # 计算回撤
    peak = nav_values[0]
    drawdowns = []
    for v in nav_values:
        if v > peak:
            peak = v
        dd = (v - peak) / peak * 100 if peak > 0 else 0
        drawdowns.append(dd)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=nav_dates,
        y=drawdowns,
        name='回撤',
        fill='tozeroy',
        line=dict(color='#b45f3d', width=1.5),
        fillcolor='rgba(180, 95, 61, 0.14)',
        hovertemplate='日期: %{x}<br>回撤: %{y:.2f}%<extra></extra>',
    ))

    fig.update_layout(
        template='plotly_white',
        paper_bgcolor='#ffffff',
        plot_bgcolor='#ffffff',
        height=280,
        margin=dict(l=54, r=24, t=20, b=34),
        yaxis=dict(title='回撤 (%)', tickformat='.1f', gridcolor='#edf2f7', zeroline=False),
        xaxis=dict(title='', gridcolor='#edf2f7', zeroline=False),
        showlegend=False,
    )

    return fig


def _metric_card(label, key, unit, color):
    """创建单个指标卡片占位"""
    return html.Div([
        html.Div(label, className='metric-label'),
        html.Div(id=f'metric-{key}', children='--', className='metric-value',
                 style={'color': color}),
        html.Div(unit, className='metric-unit'),
    ], className='metric-card', style={'--metric-color': color})


def _build_metric_card(label, display_value, color):
    """构建已填充的指标卡片"""
    return html.Div([
        html.Div(label, className='metric-label'),
        html.Div(display_value, className='metric-value', style={'color': color}),
    ], className='metric-card', style={'--metric-color': color})


# ===== 格式化函数 =====

def _fmt_pct(value, unit):
    if value is None:
        return '--'
    return f"{value:.2f}{unit}"


def _fmt_sharpe(value, unit):
    if value is None:
        return 'N/A'
    if abs(value) > 1000:
        return 'N/A'  # 异常值不显示
    return f"{value:.3f}"


def _fmt_pf(value, unit):
    if value is None:
        return 'N/A'
    return f"{value:.2f}"


def _fmt_int(value, unit):
    if value is None:
        return '--'
    return f"{int(value)}{unit}"
