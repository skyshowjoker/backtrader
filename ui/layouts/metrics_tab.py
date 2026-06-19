"""绩效指标 Tab - 关键指标卡片 + 回撤曲线"""

from dash import html, dcc
import plotly.graph_objects as go


def create_metrics_tab():
    """创建绩效指标 Tab 布局"""
    return html.Div([
        # 指标卡片网格
        html.Div(id='metrics-container', children=[
            _metric_card('总收益率', 'total_return', '%', '#2563eb'),
            _metric_card('年化收益率', 'annual_return', '%', '#7c3aed'),
            _metric_card('夏普比率', 'sharpe_ratio', '', '#059669'),
            _metric_card('最大回撤', 'max_drawdown', '%', '#dc2626'),
            _metric_card('胜率', 'win_rate', '%', '#d97706'),
            _metric_card('盈亏比', 'profit_factor', '', '#0891b2'),
            _metric_card('总交易次数', 'total_trades', '次', '#4b5563'),
            _metric_card('最大回撤持续', 'max_drawdown_duration', '天', '#9333ea'),
        ], className='metrics-grid'),

        # 回撤曲线
        html.Div([
            html.H5('📉 回撤曲线', className='section-title'),
            dcc.Graph(
                id='drawdown-chart',
                config={'displayModeBar': False},
                style={'height': '250px'},
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
        ('总收益率', 'total_return', '%', '#2563eb', _fmt_pct),
        ('年化收益率', 'annual_return', '%', '#7c3aed', _fmt_pct),
        ('夏普比率', 'sharpe_ratio', '', '#059669', _fmt_sharpe),
        ('最大回撤', 'max_drawdown', '%', '#dc2626', _fmt_pct),
        ('胜率', 'win_rate', '%', '#d97706', _fmt_pct),
        ('盈亏比', 'profit_factor', '', '#0891b2', _fmt_pf),
        ('总交易次数', 'total_trades', '次', '#4b5563', _fmt_int),
        ('最大回撤持续', 'max_drawdown_duration', '天', '#9333ea', _fmt_int),
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
                           x=0.5, y=0.5, showarrow=False, font=dict(size=14, color='#999'))
        fig.update_layout(template='plotly_white', height=250, margin=dict(l=60, r=30, t=20, b=30))
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
        line=dict(color='#ef4444', width=1),
        fillcolor='rgba(239, 68, 68, 0.15)',
        hovertemplate='日期: %{x}<br>回撤: %{y:.2f}%<extra></extra>',
    ))

    fig.update_layout(
        template='plotly_white',
        height=250,
        margin=dict(l=60, r=30, t=20, b=30),
        yaxis=dict(title='回撤 (%)', tickformat='.1f'),
        xaxis=dict(title=''),
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
    ], className='metric-card', style={'borderLeft': f'3px solid {color}'})


def _build_metric_card(label, display_value, color):
    """构建已填充的指标卡片"""
    return html.Div([
        html.Div(label, className='metric-label'),
        html.Div(display_value, className='metric-value', style={'color': color}),
    ], className='metric-card', style={'borderLeft': f'3px solid {color}'})


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
