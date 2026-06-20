"""交易记录 Tab - 已平仓交易 DataTable"""

from dash import html, dash_table


def create_trades_tab():
    """创建交易记录 Tab 布局"""
    return html.Div([
        html.Div([
            html.H3('交易记录', className='panel-title'),
            html.Span('已平仓交易明细', className='panel-subtitle'),
        ], className='panel-heading trades-heading'),
        html.Div(id='trades-table-container', children=[
            html.Div('请先运行回测', className='sidebar-hint'),
        ]),
    ], className='trades-tab')


def build_trades_table(trades):
    """构建交易记录 DataTable

    Args:
        trades: list[dict], result_extractor 返回的交易列表

    Returns:
        dash_table.DataTable
    """
    if not trades:
        return html.Div('暂无交易记录', className='sidebar-hint')

    # 格式化数据
    formatted = []
    for t in trades:
        row = {
            '标的': t.get('data_name', ''),
            '方向': _format_direction(t.get('direction', '')),
            '买入日期': t.get('entry_date', ''),
            '卖出日期': t.get('exit_date', ''),
            '买入价格': _num(t.get('entry_price', 0), 3),
            '卖出价格': _num(t.get('exit_price', 0), 3),
            '数量': _num(t.get('size', 0), 0),
            '毛利润': _num(t.get('gross_pnl', 0), 2),
            '净利润': _num(t.get('net_pnl', 0), 2),
            '持仓天数': int(t.get('duration', 0) or 0),
        }
        formatted.append(row)

    table = dash_table.DataTable(
        id='trades-datatable',
        columns=[
            {'name': '标的', 'id': '标的'},
            {'name': '方向', 'id': '方向'},
            {'name': '买入日期', 'id': '买入日期'},
            {'name': '卖出日期', 'id': '卖出日期'},
            {'name': '买入价格', 'id': '买入价格', 'type': 'numeric', 'format': {'specifier': ',.3f'}},
            {'name': '卖出价格', 'id': '卖出价格', 'type': 'numeric', 'format': {'specifier': ',.3f'}},
            {'name': '数量', 'id': '数量', 'type': 'numeric', 'format': {'specifier': ',.0f'}},
            {'name': '毛利润', 'id': '毛利润', 'type': 'numeric', 'format': {'specifier': ',.2f'}},
            {'name': '净利润', 'id': '净利润', 'type': 'numeric', 'format': {'specifier': ',.2f'}},
            {'name': '持仓天数', 'id': '持仓天数', 'type': 'numeric', 'format': {'specifier': ',.0f'}},
        ],
        data=formatted,
        sort_action='native',
        filter_action='native',
        page_size=20,
        page_action='native',
        style_table={'overflowX': 'auto', 'border': '1px solid #dde5ef', 'borderRadius': '8px'},
        style_cell={
            'textAlign': 'right',
            'padding': '10px 12px',
            'fontSize': '13px',
            'fontFamily': '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            'border': 'none',
            'borderBottom': '1px solid #edf2f7',
            'minWidth': '96px',
            'whiteSpace': 'nowrap',
        },
        style_header={
            'backgroundColor': '#f8fafc',
            'color': '#334155',
            'fontWeight': '700',
            'border': 'none',
            'borderBottom': '1px solid #d9e2ec',
        },
        style_cell_conditional=[
            {'if': {'column_id': '标的'}, 'textAlign': 'left', 'minWidth': '86px'},
            {'if': {'column_id': '方向'}, 'textAlign': 'center', 'minWidth': '72px'},
            {'if': {'column_id': '买入日期'}, 'textAlign': 'center'},
            {'if': {'column_id': '卖出日期'}, 'textAlign': 'center'},
        ],
        style_data_conditional=[
            {
                'if': {'filter_query': '{净利润} >= 0', 'column_id': '净利润'},
                'color': '#047857',
                'fontWeight': '700',
            },
            {
                'if': {'filter_query': '{净利润} < 0', 'column_id': '净利润'},
                'color': '#c2410c',
                'fontWeight': '700',
            },
        ],
        style_data={
            'backgroundColor': '#ffffff',
            'color': '#334155',
        },
    )

    # 统计信息
    total = len(trades)
    won = sum(1 for t in trades if t.get('net_pnl', 0) >= 0)
    total_pnl = sum(t.get('net_pnl', 0) for t in trades)

    stats = html.Div([
        html.Span(f"共 {total} 笔交易", className='trade-stat'),
        html.Span(f"盈利 {won} 笔", className='trade-stat trade-stat-positive'),
        html.Span(f"亏损 {total - won} 笔", className='trade-stat trade-stat-negative'),
        html.Span(f"总净利润: {total_pnl:,.2f}",
                  className='trade-stat trade-stat-positive' if total_pnl >= 0 else 'trade-stat trade-stat-negative'),
    ], className='trade-stats-bar')

    return html.Div([stats, table])


def _format_direction(direction):
    """统一交易方向显示。"""
    if direction in ('Long', 'long', '多头'):
        return '多头'
    if direction in ('Short', 'short', '空头'):
        return '空头'
    return direction or '--'


def _num(value, digits):
    """转换为 DataTable 可排序的数字。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return round(number, digits)
