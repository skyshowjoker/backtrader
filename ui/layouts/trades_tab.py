"""交易记录 Tab - 已平仓交易 DataTable"""

from dash import html, dash_table


def create_trades_tab():
    """创建交易记录 Tab 布局"""
    return html.Div([
        html.H5('📋 交易记录', className='section-title'),
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
            '方向': t.get('direction', ''),
            '买入日期': t.get('entry_date', ''),
            '卖出日期': t.get('exit_date', ''),
            '买入价格': f"{t.get('entry_price', 0):.3f}",
            '卖出价格': f"{t.get('exit_price', 0):.3f}",
            '数量': f"{t.get('size', 0):.0f}",
            '毛利润': f"{t.get('gross_pnl', 0):.2f}",
            '净利润': f"{t.get('net_pnl', 0):.2f}",
            '持仓天数': str(t.get('duration', 0)),
        }
        # 净利润着色标记
        pnl = t.get('net_pnl', 0)
        row['_pnl_positive'] = '1' if pnl >= 0 else '0'
        formatted.append(row)

    table = dash_table.DataTable(
        id='trades-datatable',
        columns=[
            {'name': '标的', 'id': '标的'},
            {'name': '方向', 'id': '方向'},
            {'name': '买入日期', 'id': '买入日期'},
            {'name': '卖出日期', 'id': '卖出日期'},
            {'name': '买入价格', 'id': '买入价格'},
            {'name': '卖出价格', 'id': '卖出价格'},
            {'name': '数量', 'id': '数量'},
            {'name': '毛利润', 'id': '毛利润'},
            {'name': '净利润', 'id': '净利润'},
            {'name': '持仓天数', 'id': '持仓天数'},
        ],
        data=formatted,
        sort_action='native',
        filter_action='native',
        page_size=20,
        page_action='native',
        style_table={'overflowX': 'auto'},
        style_cell={
            'textAlign': 'center',
            'padding': '8px 12px',
            'fontSize': '13px',
            'fontFamily': '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        },
        style_header={
            'backgroundColor': '#f8fafc',
            'fontWeight': 'bold',
            'borderBottom': '2px solid #e2e8f0',
        },
        style_data_conditional=[
            {
                'if': {'filter_query': '{净利润} > 0'},
                'color': '#16a34a',
            },
            {
                'if': {'filter_query': '{净利润} < 0'},
                'color': '#dc2626',
            },
        ],
        style_data={
            'borderBottom': '1px solid #f1f5f9',
        },
    )

    # 统计信息
    total = len(trades)
    won = sum(1 for t in trades if t.get('net_pnl', 0) >= 0)
    total_pnl = sum(t.get('net_pnl', 0) for t in trades)

    stats = html.Div([
        html.Span(f"共 {total} 笔交易", className='trade-stat'),
        html.Span(f"盈利 {won} 笔", className='trade-stat', style={'color': '#16a34a'}),
        html.Span(f"亏损 {total - won} 笔", className='trade-stat', style={'color': '#dc2626'}),
        html.Span(f"总净利润: {total_pnl:,.2f}",
                  className='trade-stat',
                  style={'color': '#16a34a' if total_pnl >= 0 else '#dc2626'}),
    ], className='trade-stats-bar')

    return html.Div([stats, table])
