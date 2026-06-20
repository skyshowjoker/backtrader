"""聚宽风格策略到 Backtrader Strategy 的轻量适配器。"""

import math
from types import SimpleNamespace

import backtrader as bt
import pandas as pd


def create_joinquant_strategy(namespace, strategy_name='JoinQuantStrategy'):
    """从聚宽 initialize/handle_data 函数创建 Backtrader 策略类。"""
    initialize = namespace.get('initialize')
    handle_data = namespace.get('handle_data')
    before_trading_start = namespace.get('before_trading_start')
    after_trading_end = namespace.get('after_trading_end')
    g = namespace.setdefault('g', SimpleNamespace())

    class JoinQuantStrategy(bt.Strategy):
        params = (('printlog', False),)

        def __init__(self):
            self.context = _Context(self, g)
            self._jq_namespace = namespace
            self._jq_initialized = False
            self._jq_scheduled_funcs = []
            self._jq_after_called = set()
            self._jq_security_aliases = {}
            self._jq_logs = []
            self._jq_log_level = 'info'
            self._jq_data_map = _build_data_map(self.datas)
            self._bind_api()

            if initialize:
                initialize(self.context)
            self._jq_initialized = True

        def next(self):
            self._update_context()
            self._bind_api()

            current_date = self.datas[0].datetime.date(0)
            if before_trading_start and current_date not in self._jq_after_called:
                before_trading_start(self.context)

            if handle_data:
                handle_data(self.context, _DataProxy(self))

            for func in list(self._jq_scheduled_funcs):
                func(self.context)

            if after_trading_end:
                after_trading_end(self.context)
                self._jq_after_called.add(current_date)

        def _bind_api(self):
            api = _JoinQuantAPI(self)
            self._jq_namespace.update({
                'g': g,
                'order': api.order,
                'order_target': api.order_target,
                'order_value': api.order_value,
                'order_target_value': api.order_target_value,
                'order_target_percent': api.order_target_percent,
                'attribute_history': api.attribute_history,
                'history': api.attribute_history,
                'get_current_data': api.get_current_data,
                'set_benchmark': api.set_benchmark,
                'set_option': api.noop,
                'set_order_cost': api.noop,
                'set_slippage': api.noop,
                'run_daily': api.run_daily,
                'log': api.log,
            })

        def _update_context(self):
            self.context.current_dt = self.datas[0].datetime.datetime(0)
            self.context.previous_date = self.datas[0].datetime.date(-1) if len(self) > 1 else None
            self.context.portfolio = _build_portfolio(self)

    JoinQuantStrategy.__name__ = strategy_name
    JoinQuantStrategy.__qualname__ = strategy_name
    JoinQuantStrategy.__doc__ = '聚宽格式策略适配器'
    return JoinQuantStrategy


class _Context(SimpleNamespace):
    def __init__(self, strategy, g):
        super().__init__()
        self.g = g
        self.current_dt = None
        self.previous_date = None
        self.portfolio = _build_portfolio(strategy)


class _DataProxy:
    def __init__(self, strategy):
        self.strategy = strategy

    def __getitem__(self, security):
        return _SecurityData(self.strategy, security)

    def current(self, security, fields):
        item = _SecurityData(self.strategy, security)
        if isinstance(fields, (list, tuple)):
            return {field: getattr(item, field) for field in fields}
        return getattr(item, fields)


class _SecurityData:
    def __init__(self, strategy, security):
        self.strategy = strategy
        self.security = security
        self.data = _resolve_data(strategy, security)

    @property
    def open(self):
        return float(self.data.open[0])

    @property
    def high(self):
        return float(self.data.high[0])

    @property
    def low(self):
        return float(self.data.low[0])

    @property
    def close(self):
        return float(self.data.close[0])

    @property
    def volume(self):
        return float(self.data.volume[0])


class _JoinQuantAPI:
    def __init__(self, strategy):
        self.strategy = strategy

    def order(self, security, amount):
        data = _resolve_data_or_none(self.strategy, security)
        if data is None or not _is_data_available(data):
            return None
        _remember_security_alias(self.strategy, security, data)
        amount = int(amount)
        if amount > 0:
            return self.strategy.buy(data=data, size=amount)
        if amount < 0:
            return self.strategy.sell(data=data, size=abs(amount))
        return None

    def order_target(self, security, amount):
        data = _resolve_data_or_none(self.strategy, security)
        if data is None or not _is_data_available(data):
            return None
        _remember_security_alias(self.strategy, security, data)
        return self.strategy.order_target_size(data=data, target=int(amount))

    def order_value(self, security, value):
        data = _resolve_data_or_none(self.strategy, security)
        if data is None or not _is_data_available(data):
            return None
        _remember_security_alias(self.strategy, security, data)
        price = float(data.close[0])
        if not _is_finite_price(price):
            return None
        order_value = abs(float(value))
        if value > 0:
            order_value = min(order_value, float(self.strategy.broker.getcash()) * 0.995)
        size = int(order_value / price)
        if size <= 0:
            return None
        if value > 0:
            return self.strategy.buy(data=data, size=size)
        if value < 0:
            return self.strategy.sell(data=data, size=size)
        return None

    def order_target_value(self, security, value):
        data = _resolve_data_or_none(self.strategy, security)
        if data is None or not _is_data_available(data):
            return None
        _remember_security_alias(self.strategy, security, data)
        price = float(data.close[0])
        if not _is_finite_price(price):
            return None

        target_value = max(0.0, float(value))
        current_size = self.strategy.getposition(data).size
        if target_value <= 0:
            target_size = 0
        else:
            # JoinQuant can target nearly all available cash.  Backtrader checks
            # commission up front, so leave a small cash buffer to avoid margin
            # rejections on all-in ETF orders.
            portfolio_value = float(self.strategy.broker.getvalue())
            capped_value = min(target_value, portfolio_value * 0.995)
            target_size = int(capped_value / price)

        if target_size == current_size:
            return None
        return self.strategy.order_target_size(data=data, target=target_size)

    def order_target_percent(self, security, percent):
        value = self.strategy.broker.getvalue() * float(percent)
        return self.order_target_value(security, value)

    def run_daily(self, func, time='every_bar', reference_security=None):
        if callable(func) and func not in self.strategy._jq_scheduled_funcs:
            self.strategy._jq_scheduled_funcs.append(func)
        return None

    def attribute_history(self, security, count, unit='1d', fields='close',
                          skip_paused=True, df=True, **kwargs):
        if isinstance(fields, str):
            fields = [fields]
        data = _resolve_data_or_none(self.strategy, security)
        if data is None:
            empty = {field: [] for field in fields}
            return pd.DataFrame(empty) if df else empty

        fast = _fast_attribute_history(self.strategy, data, count, fields, df)
        if fast is not None:
            return fast

        rows = {}
        for field in fields:
            line = getattr(data, field)
            values = list(line.get(size=int(count)))
            rows[field] = [float(value) for value in values]

        if df:
            return pd.DataFrame(rows)
        return rows

    def get_current_data(self):
        return _CurrentDataProxy(self.strategy)

    def set_benchmark(self, security):
        self.strategy.context.benchmark = security

    def noop(self, *args, **kwargs):
        return None

    @property
    def log(self):
        return _Logger(self.strategy)


class _CurrentDataProxy:
    def __init__(self, strategy):
        self.strategy = strategy

    def __getitem__(self, security):
        data = _resolve_data_or_none(self.strategy, security)
        if data is None or not _is_data_available(data):
            return SimpleNamespace(
                day_open=float('nan'),
                high_limit=float('inf'),
                low_limit=0.0,
                paused=True,
                last_price=float('nan'),
            )
        item = _SecurityData(self.strategy, security)
        return SimpleNamespace(
            day_open=item.open,
            high_limit=float('inf'),
            low_limit=0.0,
            paused=False,
            last_price=item.close,
        )


class _Logger:
    def __init__(self, strategy):
        self.strategy = strategy

    def info(self, message):
        _record_log(self.strategy, 'info', message)
        if self.strategy.p.printlog:
            print(message)

    def warn(self, message):
        _record_log(self.strategy, 'warn', message)
        if self.strategy.p.printlog:
            print(message)

    def error(self, message):
        _record_log(self.strategy, 'error', message)
        if self.strategy.p.printlog:
            print(message)

    def debug(self, message):
        _record_log(self.strategy, 'debug', message)
        if self.strategy.p.printlog:
            print(message)

    def set_level(self, *args, **kwargs):
        level = None
        for value in reversed(args):
            if isinstance(value, str) and value.lower() in _LOG_LEVELS:
                level = value.lower()
                break
        if level is None:
            level = str(kwargs.get('level', '')).lower()
        if level in _LOG_LEVELS:
            self.strategy._jq_log_level = level
        return None


def _build_portfolio(strategy):
    positions = {}
    aliases = {}
    preferred_aliases = {}
    requested_aliases = getattr(strategy, '_jq_security_aliases', {}) or {}
    for data in strategy.datas:
        name = data._name
        pos = strategy.getposition(data)
        price = _safe_line_value(data.close)
        position = SimpleNamespace(
            security=name,
            total_amount=pos.size,
            closeable_amount=pos.size,
            avg_cost=pos.price,
            price=price,
            value=pos.size * price,
        )
        positions[name] = position
        aliases[_normalize_security(name)] = name

        if name.isdigit():
            suffix = _suffix_for_code(name)
            aliases[name + suffix] = name
            preferred_aliases[name] = name + suffix

        requested = requested_aliases.get(_normalize_security(name))
        if requested:
            aliases[str(requested)] = name
            aliases[_normalize_security(requested)] = name
            preferred_aliases[name] = str(requested)

    return SimpleNamespace(
        cash=strategy.broker.getcash(),
        available_cash=strategy.broker.getcash(),
        total_value=strategy.broker.getvalue(),
        portfolio_value=strategy.broker.getvalue(),
        positions=_PositionsProxy(positions, aliases, preferred_aliases),
    )


class _PositionsProxy:
    """聚宽 positions 映射：迭代持仓，按代码/后缀代码读取仓位。"""

    def __init__(self, positions, aliases, preferred_aliases=None):
        self._positions = positions
        self._aliases = aliases
        self._preferred_aliases = preferred_aliases or {}

    def __iter__(self):
        for key, position in self._positions.items():
            if position.total_amount:
                yield self._preferred_key(key)

    def __len__(self):
        return sum(1 for _ in self)

    def __contains__(self, key):
        return self[key].total_amount != 0

    def __getitem__(self, key):
        normalized = _normalize_security(key)
        canonical = self._positions.get(key)
        if canonical is not None:
            return canonical

        alias_key = self._aliases.get(str(key)) or self._aliases.get(normalized)
        if alias_key and alias_key in self._positions:
            return self._positions[alias_key]

        return SimpleNamespace(
            security=str(key),
            total_amount=0,
            closeable_amount=0,
            avg_cost=0.0,
            price=0.0,
            value=0.0,
        )

    def keys(self):
        return list(iter(self))

    def items(self):
        return [(key, self[key]) for key in self]

    def values(self):
        return [self[key] for key in self]

    def get(self, key, default=None):
        value = self[key]
        if value.total_amount == 0 and default is not None:
            return default
        return value

    def _preferred_key(self, key):
        if key in self._preferred_aliases:
            return self._preferred_aliases[key]
        if key.isdigit():
            suffix = _suffix_for_code(key)
            return key + suffix
        return key


def _resolve_data_or_none(strategy, security):
    try:
        return _resolve_data(strategy, security)
    except KeyError:
        return None


def _resolve_data(strategy, security):
    code = _normalize_security(security)
    data_map = getattr(strategy, '_jq_data_map', None)
    if data_map:
        found = data_map.get(str(security)) or data_map.get(code)
        if found is not None:
            return found

    for data in strategy.datas:
        if data._name == code or _normalize_security(data._name) == code:
            return data

    for data in strategy.datas:
        if code in data._name or data._name in code:
            return data

    raise KeyError(f'未加载证券数据: {security}')


def _remember_security_alias(strategy, security, data):
    aliases = getattr(strategy, '_jq_security_aliases', None)
    if aliases is None:
        return
    aliases[_normalize_security(data._name)] = str(security)


def _record_log(strategy, level, message):
    logs = getattr(strategy, '_jq_logs', None)
    if logs is None:
        return
    if _LOG_LEVELS.get(level, 20) < _LOG_LEVELS.get(getattr(strategy, '_jq_log_level', 'info'), 20):
        return
    current_dt = getattr(getattr(strategy, 'context', None), 'current_dt', None)
    date = current_dt.strftime('%Y-%m-%d %H:%M:%S') if current_dt else ''
    logs.append({
        'date': date,
        'level': level,
        'message': str(message),
    })


def _fast_attribute_history(strategy, data, count, fields, as_dataframe):
    arrays = getattr(data, '_bt_arrays', None)
    date_to_pos = getattr(data, '_bt_date_to_pos', None)
    if not arrays or not date_to_pos:
        return None

    try:
        current_date = strategy.datas[0].datetime.date(0)
        pos = date_to_pos.get(current_date)
        if pos is None:
            return None
        start = max(0, pos - int(count) + 1)
        rows = {}
        for field in fields:
            values = arrays.get(field)
            if values is None:
                return None
            rows[field] = values[start:pos + 1].copy()
        if as_dataframe:
            return pd.DataFrame(rows)
        return {field: values.tolist() for field, values in rows.items()}
    except Exception:
        return None


def _is_data_available(data):
    if data is None or not len(data):
        return False
    return _is_finite_price(_safe_line_value(data.close))


def _safe_line_value(line, default=float('nan')):
    try:
        value = float(line[0])
    except Exception:
        return default
    return value if _is_finite_price(value) else default


def _is_finite_price(value):
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except Exception:
        return False


def _normalize_security(security):
    security = str(security)
    return security.split('.')[0]


def _build_data_map(datas):
    data_map = {}
    for data in datas:
        name = str(getattr(data, '_name', '') or '')
        normalized = _normalize_security(name)
        if name:
            data_map[name] = data
        if normalized:
            data_map[normalized] = data
            data_map[normalized + _suffix_for_code(normalized)] = data
    return data_map


_LOG_LEVELS = {
    'debug': 10,
    'info': 20,
    'warn': 30,
    'warning': 30,
    'error': 40,
}


def _suffix_for_code(code):
    code = str(code or '')
    return '.XSHG' if code.startswith(('5', '6', '9')) else '.XSHE'
