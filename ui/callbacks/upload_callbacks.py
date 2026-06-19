"""自定义策略上传回调 - 安全检查 + 注册"""

import ast
import base64
import io

import backtrader as bt
from dash import Input, Output, State, html, no_update

from ui.utils.sandbox import validate_strategy_code, execute_strategy_code
from ui.strategies.registry import StrategyRegistry


def register_upload_callbacks(app):
    """注册策略上传相关回调"""

    @app.callback(
        [
            Output('upload-status', 'children'),
            Output('strategy-selector', 'options', allow_duplicate=True),
        ],
        [Input('upload-strategy', 'contents')],
        [State('upload-strategy', 'filename')],
        prevent_initial_call=True,
    )
    def upload_strategy(contents, filename):
        """处理策略文件上传"""
        if not contents:
            return no_update, no_update

        # 1. 解码文件内容
        try:
            content_type, content_string = contents.split(',')
            decoded = base64.b64decode(content_string).decode('utf-8')
        except Exception as e:
            return html.Span(f'❌ 文件读取失败: {e}', style={'color': '#dc2626'}), no_update

        # 2. 验证文件名
        if not filename or not filename.endswith('.py'):
            return html.Span('❌ 请上传 .py 文件', style={'color': '#dc2626'}), no_update

        # 3. 安全检查
        is_valid, error_msg = validate_strategy_code(decoded)
        if not is_valid:
            return html.Span(f'❌ {error_msg}', style={'color': '#dc2626'}), no_update

        # 4. 执行代码，提取策略类
        strategy_class, exec_error = execute_strategy_code(decoded, filename)
        if exec_error:
            return html.Span(f'❌ {exec_error}', style={'color': '#dc2626'}), no_update

        if strategy_class is None:
            return html.Span('❌ 未找到 bt.Strategy 子类', style={'color': '#dc2626'}), no_update

        # 5. 注册策略
        strategy_name = strategy_class.__name__
        try:
            StrategyRegistry.register(
                name=strategy_name,
                strategy_class=strategy_class,
                description=f'自定义策略 ({filename})',
                category='custom',
            )
        except Exception as e:
            return html.Span(f'❌ 注册失败: {e}', style={'color': '#dc2626'}), no_update

        # 6. 更新下拉选项
        options = StrategyRegistry.get_dropdown_options()

        status = html.Div([
            html.Span(f'✅ 策略 "{strategy_name}" 已注册', style={'color': '#16a34a'}),
        ])

        return status, options
