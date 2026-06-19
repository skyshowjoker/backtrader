"""策略选择回调 - 动态参数 UI 生成 + 参数值缓存"""

import json
from dash import Input, Output, State, callback_context, no_update, html, dcc, ALL, MATCH

from ui.strategies.registry import StrategyRegistry


def register_strategy_callbacks(app):
    """注册策略相关回调"""

    # ===== 初始化策略下拉选项 =====
    @app.callback(
        Output('strategy-selector', 'options'),
        Input('strategy-selector', 'value'),
    )
    def update_dropdown_options(_):
        """始终返回最新的策略列表"""
        return StrategyRegistry.get_dropdown_options()

    # ===== 策略选择 → 动态参数 UI =====
    @app.callback(
        [
            Output('params-container', 'children'),
            Output('params-store', 'data'),
        ],
        [Input('strategy-selector', 'value')],
        prevent_initial_call=False,
    )
    def on_strategy_selected(strategy_name):
        """策略选择变化 → 更新参数 UI 和参数缓存"""
        if not strategy_name:
            return [html.Div('请先选择策略', className='sidebar-hint')], None

        # 获取参数 schema
        params_schema = StrategyRegistry.get_params(strategy_name)

        if not params_schema:
            return [html.Div('该策略无可配置参数', className='sidebar-hint')], json.dumps({})

        # 动态生成参数输入组件
        param_components = []
        default_params = {}
        for p in params_schema:
            comp = _create_param_component(p)
            param_components.append(comp)
            default_params[p['name']] = p['default']

        return param_components, json.dumps(default_params)

    # ===== 参数值变化 → 更新参数缓存 =====
    @app.callback(
        Output('params-store', 'data', allow_duplicate=True),
        Input({'type': 'param-input', 'index': ALL}, 'value'),
        State('strategy-selector', 'value'),
        prevent_initial_call=True,
    )
    def on_param_change(param_values, strategy_name):
        """参数输入变化 → 更新参数存储"""
        if not strategy_name:
            return no_update

        params_schema = StrategyRegistry.get_params(strategy_name)
        params = {}
        for i, p in enumerate(params_schema):
            if i < len(param_values) and param_values[i] is not None:
                # 类型转换
                value = param_values[i]
                if p['type'] == 'bool':
                    value = bool(value)
                elif p['type'] == 'int':
                    value = int(value)
                elif p['type'] == 'float':
                    value = float(value)
                params[p['name']] = value
            else:
                params[p['name']] = p['default']

        return json.dumps(params)


def _create_param_component(param_schema):
    """根据参数 schema 创建 UI 组件

    使用 pattern-matching callback ID: {'type': 'param-input', 'index': param_name}
    """
    name = param_schema['name']
    ptype = param_schema['type']
    default = param_schema['default']
    label = param_schema['label']

    comp_id = {'type': 'param-input', 'index': name}

    if ptype == 'bool':
        component = dcc.Checklist(
            id=comp_id,
            options=[{'label': ' 启用', 'value': True}],
            value=[default] if default else [],
            inline=True,
            inputStyle={'margin-right': '5px'},
        )
    elif ptype == 'int':
        component = dcc.Input(
            id=comp_id,
            type='number',
            value=default,
            step=1,
            className='param-input',
            debounce=True,
        )
    elif ptype == 'float':
        component = dcc.Input(
            id=comp_id,
            type='number',
            value=default,
            step=0.1,
            className='param-input',
            debounce=True,
        )
    else:
        component = dcc.Input(
            id=comp_id,
            type='text',
            value=str(default) if default is not None else '',
            className='param-input',
            debounce=True,
        )

    return html.Div([
        html.Label(label, className='param-label'),
        component,
    ], className='param-row')
