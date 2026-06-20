"""Backtrader UI API server.

This module exposes the backtesting engine through a small JSON API so the
frontend can live outside Dash.  Run with:

    python -m ui.api
"""

import base64
import os
import re
from datetime import datetime

from flask import Flask, jsonify, request

from ui.engines.data_fetcher import BENCHMARK_POOL, ETF_POOL, download_data
from ui.engines.runner import check_result, start_backtest
from ui.strategies.registry import StrategyRegistry
from ui.strategies.sma_cross import SMACrossStrategy
from ui.utils.sandbox import execute_strategy_code, validate_strategy_code

_TASK_HISTORY = {}
_MAX_TASK_HISTORY = 50


def create_app():
    """Create the API app and register built-in strategies."""
    _register_default_strategies()

    app = Flask(__name__)

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    @app.route('/api/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok'})

    @app.route('/api/meta', methods=['GET'])
    def meta():
        return jsonify({
            'strategies': _strategy_payload(),
            'etfs': _pool_payload(ETF_POOL),
            'benchmarks': _pool_payload(BENCHMARK_POOL),
            'templates': _strategy_templates(),
            'defaults': {
                'strategy': _default_strategy_name(),
                'data_codes': _default_data_codes(),
                'benchmark': '000300',
                'start_date': '2020-01-01',
                'end_date': '2025-12-31',
                'initial_cash': '1000000',
                'commission': '0.0002',
                'frequency': 'daily',
            },
        })

    @app.route('/api/backtests', methods=['GET'])
    def list_backtests():
        for task_id in list(_TASK_HISTORY):
            _sync_task_meta(task_id)
        tasks = sorted(
            _TASK_HISTORY.values(),
            key=lambda item: item.get('created_at', ''),
            reverse=True,
        )
        return jsonify({'tasks': tasks})

    @app.route('/api/backtests', methods=['POST', 'OPTIONS'])
    def create_backtest():
        if request.method == 'OPTIONS':
            return ('', 204)

        payload = request.get_json(silent=True) or {}
        strategy_name = payload.get('strategy')
        if not strategy_name:
            return _api_error('请选择策略', 400)

        strategy_class = StrategyRegistry.get_class(strategy_name)
        if strategy_class is None:
            return _api_error(f'策略未找到: {strategy_name}', 404)

        data_codes = payload.get('data_codes') or []
        if not isinstance(data_codes, list) or not data_codes:
            return _api_error('请至少选择一个标的', 400)

        start_date = payload.get('start_date') or '2020-01-01'
        end_date = payload.get('end_date') or '2025-12-31'
        if start_date > end_date:
            return _api_error('开始日期不能晚于结束日期', 400)

        try:
            initial_cash = _parse_non_negative_float(
                payload.get('initial_cash'), 1000000, '初始资金')
            commission = _parse_non_negative_float(
                payload.get('commission'), 0.0002, '佣金率')
        except ValueError as exc:
            return _api_error(str(exc), 400)

        params = payload.get('params') or {}
        config = {
            'start_date': start_date,
            'end_date': end_date,
            'initial_cash': initial_cash,
            'commission': commission,
            'benchmark': payload.get('benchmark') or '000300',
            'data_codes': data_codes,
            'data_type': payload.get('data_type') or 'etf',
        }

        try:
            task_id = start_backtest(strategy_class, params, config)
        except Exception as exc:
            return _api_error(f'启动失败: {exc}', 500)

        _TASK_HISTORY[task_id] = {
            'task_id': task_id,
            'strategy': strategy_name,
            'params': params,
            'config': config,
            'status': 'running',
            'message': '准备加载行情数据',
            'created_at': _now_iso(),
            'updated_at': _now_iso(),
            'summary': {},
        }
        _trim_task_history()

        return jsonify({'task_id': task_id, 'status': 'running'})

    @app.route('/api/backtests/<task_id>', methods=['GET'])
    def get_backtest(task_id):
        result = check_result(task_id)
        status = result.get('status')
        if status == 'unknown':
            return _api_error('未找到回测任务', 404)
        _sync_task_meta(task_id, result)
        return jsonify(result)

    @app.route('/api/market/series', methods=['GET', 'POST', 'OPTIONS'])
    def market_series():
        if request.method == 'OPTIONS':
            return ('', 204)

        payload = request.get_json(silent=True) or {}
        raw_codes = payload.get('codes') if request.method == 'POST' else request.args.get('codes')
        codes = _parse_codes(raw_codes)
        if not codes:
            return _api_error('请输入至少一个标的代码', 400)

        start_date = (
            payload.get('start_date')
            if request.method == 'POST'
            else request.args.get('start_date')
        ) or '2020-01-01'
        end_date = (
            payload.get('end_date')
            if request.method == 'POST'
            else request.args.get('end_date')
        ) or datetime.now().strftime('%Y-%m-%d')
        if start_date > end_date:
            return _api_error('开始日期不能晚于结束日期', 400)

        data_type = (
            payload.get('data_type')
            if request.method == 'POST'
            else request.args.get('data_type')
        ) or 'auto'

        try:
            start_ymd = _to_yyyymmdd(start_date)
            end_ymd = _to_yyyymmdd(end_date)
        except ValueError as exc:
            return _api_error(str(exc), 400)

        series = []
        errors = []
        for code in codes[:12]:
            try:
                df = download_data(code, start_ymd, end_ymd, data_type=data_type)
                item = _market_series_payload(code, df)
                if item:
                    series.append(item)
                else:
                    errors.append({'code': code, 'message': '未获取到行情数据'})
            except Exception as exc:
                errors.append({'code': code, 'message': str(exc)})

        return jsonify({'series': series, 'errors': errors})

    @app.route('/api/strategies/upload', methods=['POST', 'OPTIONS'])
    def upload_strategy():
        if request.method == 'OPTIONS':
            return ('', 204)

        strategy_format = request.form.get('strategy_format', 'auto')
        upload = request.files.get('file')
        source_code = request.form.get('source_code')
        filename = request.form.get('filename') or 'custom_strategy.py'

        if upload is not None:
            filename = upload.filename or filename
            source_code = upload.read().decode('utf-8')

        if not source_code:
            return _api_error('策略内容为空', 400)
        if not filename.endswith('.py'):
            return _api_error('请上传 .py 文件', 400)

        valid, error_msg = validate_strategy_code(source_code, strategy_format)
        if not valid:
            return _api_error(error_msg, 400)

        strategy_class, exec_error = execute_strategy_code(
            source_code, filename, strategy_format)
        if exec_error:
            return _api_error(exec_error, 400)
        if strategy_class is None:
            return _api_error('未找到 bt.Strategy 子类或聚宽策略入口', 400)

        strategy_name = strategy_class.__name__
        format_label = '聚宽策略' if strategy_name.endswith('JQ') else '自定义策略'
        StrategyRegistry.register(
            name=strategy_name,
            strategy_class=strategy_class,
            description=f'{format_label} ({filename})',
            category='custom',
        )

        return jsonify({
            'strategy': strategy_name,
            'strategies': _strategy_payload(),
        })

    @app.route('/api/strategies/upload-base64', methods=['POST', 'OPTIONS'])
    def upload_strategy_base64():
        if request.method == 'OPTIONS':
            return ('', 204)

        payload = request.get_json(silent=True) or {}
        contents = payload.get('contents', '')
        filename = payload.get('filename') or 'custom_strategy.py'
        strategy_format = payload.get('strategy_format') or 'auto'

        try:
            encoded = contents.split(',', 1)[1] if ',' in contents else contents
            source_code = base64.b64decode(encoded).decode('utf-8')
        except Exception as exc:
            return _api_error(f'文件读取失败: {exc}', 400)

        with app.test_request_context(
            '/api/strategies/upload',
            method='POST',
            data={
                'source_code': source_code,
                'filename': filename,
                'strategy_format': strategy_format,
            },
        ):
            return upload_strategy()

    return app


def _register_default_strategies():
    """Register built-in strategies for API-only runs."""
    StrategyRegistry.register(
        name='SMA双均线交叉',
        strategy_class=SMACrossStrategy,
        description='短期均线上穿长期均线买入，下穿卖出',
        category='builtin',
    )

    try:
        from ui.strategies.etf_rotate import register_etf_strategy
        register_etf_strategy()
    except Exception:
        pass

    try:
        from ui.strategies.joinquant_builtin import register_joinquant_etf_strategy
        register_joinquant_etf_strategy()
    except Exception:
        pass


def _strategy_payload():
    strategies = []
    for name in StrategyRegistry.list_all():
        info = StrategyRegistry.get(name) or {}
        strategy_class = info.get('class')
        strategies.append({
            'name': name,
            'description': info.get('description', ''),
            'category': info.get('category', 'builtin'),
            'params': info.get('params', []),
            'preferred_data_codes': getattr(strategy_class, '_preferred_data_codes', []),
        })
    return strategies


def _pool_payload(pool):
    return [
        {'code': code, 'name': name, 'label': f'{code} {name}'}
        for code, name in pool.items()
    ]


def _parse_codes(raw_codes):
    if isinstance(raw_codes, list):
        values = raw_codes
    else:
        values = re.split(r'[\s,，;；]+', str(raw_codes or ''))

    codes = []
    for value in values:
        code = _normalize_code(value)
        if code and code not in codes:
            codes.append(code)
    return codes


def _normalize_code(value):
    match = re.search(r'\d{6}', str(value or ''))
    return match.group(0) if match else ''


def _to_yyyymmdd(value):
    value = str(value or '').strip()
    try:
        return datetime.strptime(value, '%Y-%m-%d').strftime('%Y%m%d')
    except ValueError:
        pass
    if re.fullmatch(r'\d{8}', value):
        return value
    raise ValueError('日期格式应为 YYYY-MM-DD')


def _market_series_payload(code, df):
    if df is None or df.empty or 'close' not in df:
        return None

    closes = df['close'].dropna()
    if closes.empty:
        return None

    first = float(closes.iloc[0])
    if not first:
        return None

    dates = [idx.strftime('%Y-%m-%d') for idx in closes.index]
    prices = [round(float(value), 6) for value in closes]
    normalized = [round(float(value) / first, 6) for value in closes]
    returns = [round((float(value) / first - 1) * 100, 4) for value in closes]

    return {
        'code': code,
        'name': ETF_POOL.get(code) or BENCHMARK_POOL.get(code) or code,
        'dates': dates,
        'prices': prices,
        'normalized': normalized,
        'returns': returns,
    }


def _strategy_templates():
    """Return editable templates for the React code editor."""
    return {
        'joinquant': """# 聚宽风格策略示例
def initialize(context):
    set_benchmark('000300.XSHG')
    g.security = '510300'
    g.lookback = 20


def handle_data(context, data):
    prices = attribute_history(g.security, g.lookback, '1d', ['close'])
    mean_price = prices['close'].mean()
    current_price = data.current(g.security, 'close')

    if current_price > mean_price:
        order_target_percent(g.security, 1.0)
    else:
        order_target_percent(g.security, 0)
""",
        'backtrader': """import backtrader as bt


class CustomSmaStrategy(bt.Strategy):
    params = (
        ('fast', 10),
        ('slow', 30),
    )

    def __init__(self):
        self.fast = bt.ind.SMA(period=self.p.fast)
        self.slow = bt.ind.SMA(period=self.p.slow)
        self.cross = bt.ind.CrossOver(self.fast, self.slow)
        self.order = None

    def next(self):
        if self.order:
            return
        if not self.position and self.cross[0] > 0:
            self.order = self.buy()
        elif self.position and self.cross[0] < 0:
            self.order = self.sell()

    def notify_order(self, order):
        if order.status not in [order.Submitted, order.Accepted]:
            self.order = None
""",
    }


def _default_strategy_name():
    preferred = 'ETF轮动最终优化（聚宽）'
    if StrategyRegistry.get(preferred):
        return preferred
    names = StrategyRegistry.list_all()
    return names[0] if names else ''


def _default_data_codes():
    strategy_class = StrategyRegistry.get_class(_default_strategy_name())
    codes = getattr(strategy_class, '_preferred_data_codes', []) if strategy_class else []
    return codes or ['510300']


def _parse_non_negative_float(value, default, label):
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


def _now_iso():
    return datetime.now().isoformat(timespec='seconds')


def _sync_task_meta(task_id, result=None):
    """Keep API task history aligned with the runner store."""
    if task_id not in _TASK_HISTORY:
        return

    result = result or check_result(task_id)
    meta = _TASK_HISTORY[task_id]
    meta['status'] = result.get('status', meta.get('status'))
    meta['message'] = result.get('message', meta.get('message', ''))
    meta['updated_at'] = _now_iso()

    data = result.get('data')
    if isinstance(data, dict):
        metrics = data.get('metrics') or {}
        meta['summary'] = {
            'total_return': metrics.get('total_return'),
            'annual_return': metrics.get('annual_return'),
            'max_drawdown': metrics.get('max_drawdown'),
            'sharpe_ratio': metrics.get('sharpe_ratio'),
            'signals': len(data.get('signals') or []),
            'trades': len(data.get('trades') or []),
            'orders': len(data.get('orders') or []),
            'positions': len(data.get('positions') or []),
            'logs': len(data.get('logs') or []),
            'final_value': data.get('final_value'),
        }
    elif result.get('status') == 'error':
        meta['summary'] = {'error': data}


def _trim_task_history():
    if len(_TASK_HISTORY) <= _MAX_TASK_HISTORY:
        return

    removable = sorted(
        _TASK_HISTORY.items(),
        key=lambda item: item[1].get('created_at', ''),
    )
    for task_id, _ in removable[:len(_TASK_HISTORY) - _MAX_TASK_HISTORY]:
        _TASK_HISTORY.pop(task_id, None)


def _api_error(message, status):
    return jsonify({'error': message}), status


app = create_app()


if __name__ == '__main__':
    port = int(os.environ.get('BACKTRADER_API_PORT', '8060'))
    app.run(host='127.0.0.1', port=port, debug=False)
