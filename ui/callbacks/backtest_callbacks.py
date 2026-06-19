"""回测运行回调 - 运行回测、轮询结果、填充图表和指标"""

import json
from dash import Input, Output, State, callback_context, no_update, html
import dash_bootstrap_components as dbc

from ui.engines.runner import start_backtest, check_result
from ui.strategies.registry import StrategyRegistry
from ui.layouts.chart_tab import build_chart_figure
from ui.layouts.metrics_tab import build_metrics_content, build_drawdown_chart
from ui.layouts.trades_tab import build_trades_table


def register_backtest_callbacks(app):
    """注册回测相关回调"""

    # ===== 运行回测 =====
    @app.callback(
        [
            Output('task-id-store', 'data'),
            Output('interval-component', 'disabled'),
            Output('status-message', 'children'),
        ],
        [Input('run-button', 'n_clicks')],
        [
            State('strategy-selector', 'value'),
            State('date-range', 'start_date'),
            State('date-range', 'end_date'),
            State('initial-cash', 'value'),
            State('commission', 'value'),
            State('benchmark-selector', 'value'),
            State('data-codes', 'value'),
            State('params-store', 'data'),
        ],
        prevent_initial_call=True,
    )
    def run_backtest_callback(n_clicks, strategy_name, start_date, end_date,
                              initial_cash, commission, benchmark, data_codes,
                              params_json):
        """点击运行回测按钮 → 启动异步回测"""
        if not n_clicks or not strategy_name:
            return no_update, True, html.Span('请先选择策略', style={'color': '#dc2626'})

        # 获取策略类
        strategy_class = StrategyRegistry.get_class(strategy_name)
        if not strategy_class:
            return no_update, True, html.Span(f'策略未找到: {strategy_name}', style={'color': '#dc2626'})

        # 读取策略参数
        params = _read_params(strategy_name, params_json)

        # 配置
        config = {
            'start_date': start_date,
            'end_date': end_date,
            'initial_cash': float(initial_cash) if initial_cash else 1000000,
            'commission': float(commission) if commission else 0.0002,
            'benchmark': benchmark or '000300',
            'data_codes': data_codes or ['510300'],
            'data_type': 'etf',
        }

        # 启动异步回测
        try:
            task_id = start_backtest(strategy_class, params, config)
        except Exception as e:
            return no_update, True, html.Span(f'启动失败: {e}', style={'color': '#dc2626'})

        status_msg = html.Div([
            dbc.Spinner(size='sm', color='primary'),
            html.Span(' 回测运行中...', style={'marginLeft': '8px', 'color': '#2563eb'}),
        ], style={'display': 'flex', 'alignItems': 'center'})

        return task_id, False, status_msg

    # ===== 轮询结果 =====
    @app.callback(
        [
            Output('nav-chart', 'figure'),
            Output('metrics-container', 'children'),
            Output('drawdown-chart', 'figure'),
            Output('trades-table-container', 'children'),
            Output('backtest-results', 'data'),
            Output('chart-placeholder', 'style'),
            Output('status-message', 'children', allow_duplicate=True),
            Output('interval-component', 'disabled', allow_duplicate=True),
        ],
        [Input('interval-component', 'n_intervals')],
        [
            State('task-id-store', 'data'),
            State('chart-toggles', 'value'),
        ],
        prevent_initial_call=True,
    )
    def poll_result(n_intervals, task_id, toggles):
        """轮询回测结果"""
        if not task_id:
            return (no_update,) * 8

        result_info = check_result(task_id)

        if result_info['status'] == 'running':
            return (no_update,) * 8

        if result_info['status'] == 'error':
            error_msg = html.Span(f"回测失败: {result_info['data']}", style={'color': '#dc2626'})
            return (no_update,) * 5 + ({'display': 'none'}, error_msg, True)

        # 回测完成
        result = result_info['data']
        toggles = toggles or ['strategy_nav', 'benchmark_nav', 'signals']

        # 构建图表
        fig = build_chart_figure(result, toggles)

        # 构建指标
        metrics_cards = build_metrics_content(result.get('metrics', {}))

        # 构建回撤图
        dd_fig = build_drawdown_chart(result)

        # 构建交易表
        trades_table = build_trades_table(result.get('trades', []))

        # 状态消息
        total_return = result.get('metrics', {}).get('total_return', 0)
        final_value = result.get('final_value', 0)
        status_msg = html.Div([
            html.Span('回测完成', style={'color': '#16a34a', 'fontWeight': 'bold'}),
            html.Br(),
            html.Span(f"总收益: {total_return:.2f}% | 终值: {final_value:,.0f}",
                      style={'fontSize': '12px', 'color': '#4b5563'}),
        ])

        # 隐藏占位符
        placeholder_style = {'display': 'none'}

        # 缓存结果
        result_json = _serialize_result(result)

        return fig, metrics_cards, dd_fig, trades_table, result_json, placeholder_style, status_msg, True

    # ===== 图表切换 =====
    @app.callback(
        Output('nav-chart', 'figure', allow_duplicate=True),
        [Input('chart-toggles', 'value')],
        [State('backtest-results', 'data')],
        prevent_initial_call=True,
    )
    def toggle_chart(toggles, result_json):
        """图表曲线显示/隐藏切换"""
        if not result_json:
            return no_update

        result = _deserialize_result(result_json)
        return build_chart_figure(result, toggles)


def _read_params(strategy_name, params_json):
    """读取策略参数

    优先使用 params-store（由 strategy_callbacks 更新），
    回退到注册表默认值。
    """
    # 尝试从 Store 读取
    if params_json:
        try:
            params = json.loads(params_json)
            if params:
                return params
        except (json.JSONDecodeError, TypeError):
            pass

    # 回退到默认值
    params_schema = StrategyRegistry.get_params(strategy_name)
    params = {}
    for p in params_schema:
        params[p['name']] = p['default']
    return params


def _serialize_result(result):
    """将结果序列化为 JSON（供 dcc.Store 使用）"""
    try:
        serializable = {}
        for key, value in result.items():
            if isinstance(value, (list, dict, str, int, float, bool, type(None))):
                serializable[key] = value
            else:
                serializable[key] = str(value)
        return json.dumps(serializable, ensure_ascii=False)
    except Exception:
        return None


def _deserialize_result(result_json):
    """从 JSON 反序列化结果"""
    try:
        return json.loads(result_json)
    except Exception:
        return {}
