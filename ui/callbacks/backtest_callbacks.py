"""回测运行回调 - 运行回测、轮询结果、填充图表和指标"""

import json
from dash import Input, Output, State, no_update, html
import dash_bootstrap_components as dbc

from ui.engines.runner import start_backtest, check_result
from ui.strategies.registry import StrategyRegistry
from ui.layouts.chart_tab import (build_chart_figure,
                                  build_signal_analysis_figure,
                                  build_signal_summary)
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
            return no_update, True, html.Span('请先选择策略', className='status-error')

        if not start_date or not end_date:
            return no_update, True, html.Span('请选择完整日期范围', className='status-error')

        if start_date > end_date:
            return no_update, True, html.Span('开始日期不能晚于结束日期', className='status-error')

        if not data_codes:
            return no_update, True, html.Span('请至少选择一个标的代码', className='status-error')

        # 获取策略类
        strategy_class = StrategyRegistry.get_class(strategy_name)
        if not strategy_class:
            return no_update, True, html.Span(f'策略未找到: {strategy_name}', className='status-error')

        # 读取策略参数
        params = _read_params(strategy_name, params_json)

        # 配置
        config = {
            'start_date': start_date,
            'end_date': end_date,
            'benchmark': benchmark or '000300',
            'data_codes': data_codes or ['510300'],
            'data_type': 'etf',
        }

        try:
            config['initial_cash'] = _parse_non_negative_float(
                initial_cash, 1000000, '初始资金')
            config['commission'] = _parse_non_negative_float(
                commission, 0.0002, '佣金率')
        except ValueError as e:
            return no_update, True, html.Span(str(e), className='status-error')

        # 启动异步回测
        try:
            task_id = start_backtest(strategy_class, params, config)
        except Exception as e:
            return no_update, True, html.Span(f'启动失败: {e}', className='status-error')

        status_msg = html.Div([
            dbc.Spinner(size='sm', color='primary'),
            html.Span('回测运行中...', className='status-running-text'),
        ], className='status-running')

        return task_id, False, status_msg

    # ===== 轮询结果 =====
    @app.callback(
        [
            Output('nav-chart', 'figure'),
            Output('metrics-container', 'children'),
            Output('drawdown-chart', 'figure'),
            Output('trades-table-container', 'children'),
            Output('signal-analysis-chart', 'figure'),
            Output('signal-summary-content', 'children'),
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
            return (no_update,) * 10

        result_info = check_result(task_id)

        if result_info['status'] == 'running':
            partial = result_info.get('data')
            if not partial:
                status_msg = _running_status(result_info.get('message') or '回测运行中...')
                return (no_update,) * 8 + (status_msg, False)

            toggles = toggles or ['strategy_nav', 'strategy_return',
                                  'benchmark_return', 'excess_return', 'signals']
            fig = build_chart_figure(partial, toggles)
            signal_fig = build_signal_analysis_figure(partial)
            signal_summary = build_signal_summary(partial)
            result_json = _serialize_result(partial)
            status_msg = _running_status(result_info.get('message') or '数据加载中...')

            return (
                fig,
                no_update,
                no_update,
                no_update,
                signal_fig,
                signal_summary,
                result_json,
                {'display': 'none'},
                status_msg,
                False,
            )

        if result_info['status'] == 'error':
            error_msg = html.Span(f"回测失败: {result_info['data']}", className='status-error')
            return (no_update,) * 7 + ({'display': 'none'}, error_msg, True)

        if result_info['status'] != 'done':
            error_msg = html.Span('未找到回测任务，请重新运行', className='status-error')
            return (no_update,) * 7 + ({'display': 'none'}, error_msg, True)

        # 回测完成
        result = result_info['data']
        toggles = toggles or ['strategy_nav', 'strategy_return',
                              'benchmark_return', 'excess_return', 'signals']

        # 构建图表
        fig = build_chart_figure(result, toggles)

        # 构建指标
        metrics_cards = build_metrics_content(result.get('metrics', {}))

        # 构建回撤图
        dd_fig = build_drawdown_chart(result)

        # 构建交易表
        trades_table = build_trades_table(result.get('trades', []))

        # 构建信号分析
        signal_fig = build_signal_analysis_figure(result)
        signal_summary = build_signal_summary(result)

        # 状态消息
        total_return = result.get('metrics', {}).get('total_return', 0)
        final_value = result.get('final_value', 0)
        benchmark_source = _format_benchmark_source(result.get('benchmark_source'))
        status_msg = html.Div([
            html.Span('回测完成', className='status-success-title'),
            html.Span(f"总收益: {total_return:.2f}% | 终值: {final_value:,.0f}{benchmark_source}",
                      className='status-success-detail'),
        ], className='status-success')

        # 隐藏占位符
        placeholder_style = {'display': 'none'}

        # 缓存结果
        result_json = _serialize_result(result)

        return (
            fig,
            metrics_cards,
            dd_fig,
            trades_table,
            signal_fig,
            signal_summary,
            result_json,
            placeholder_style,
            status_msg,
            True,
        )

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


def _parse_non_negative_float(value, default, label):
    """解析顶部工具条中的数值输入。"""
    if value is None or str(value).strip() == '':
        return default

    normalized = str(value).replace(',', '').strip()
    try:
        number = float(normalized)
    except ValueError:
        raise ValueError(f'{label}必须是数字')

    if number < 0:
        raise ValueError(f'{label}不能为负数')
    return number


def _running_status(message):
    """构建运行中状态。"""
    return html.Div([
        dbc.Spinner(size='sm', color='primary'),
        html.Span(message, className='status-running-text'),
    ], className='status-running')


def _format_benchmark_source(source):
    """展示基准兜底来源。"""
    if source and source.startswith('proxy:'):
        return f" | 基准代用: {source.split(':', 1)[1]}"
    return ''
