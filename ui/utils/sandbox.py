"""自定义策略安全执行模块

提供 AST 级别的安全检查和受限命名空间执行。
适用于本地/个人使用场景，非加密级安全。
"""

import ast
import inspect
import math
from types import SimpleNamespace

import backtrader as bt
import numpy as np
import pandas as pd

from ui.utils.joinquant_adapter import create_joinquant_strategy


# 危险的 AST 节点类型和名称
_DANGEROUS_IMPORTS = {'os', 'subprocess', 'shutil', 'sys', 'socket', 'http',
                      'urllib', 'requests', 'pickle', 'marshal', 'ctypes',
                      'multiprocessing', 'threading', 'signal', 'resource'}

_DANGEROUS_CALLS = {'__import__', 'eval', 'exec', 'compile', 'open',
                    'input', 'breakpoint', 'exit', 'quit'}

_DANGEROUS_ATTRS = {'__class__', '__bases__', '__subclasses__', '__globals__',
                    '__code__', '__func__', '__self__', '__dict__',
                    '__module__', '__weakref__'}


class StrategyValidator(ast.NodeVisitor):
    """AST 遍历器，检查代码中的危险构造"""

    def __init__(self):
        self.errors = []

    def visit_Import(self, node):
        for alias in node.names:
            root_module = alias.name.split('.')[0]
            if root_module in _DANGEROUS_IMPORTS:
                self.errors.append(f"禁止导入模块: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            root_module = node.module.split('.')[0]
            if root_module in _DANGEROUS_IMPORTS:
                self.errors.append(f"禁止从模块导入: {node.module}")
        self.generic_visit(node)

    def visit_Call(self, node):
        # 检查函数调用
        if isinstance(node.func, ast.Name):
            if node.func.id in _DANGEROUS_CALLS:
                self.errors.append(f"禁止调用函数: {node.func.id}()")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        # 检查危险属性访问
        if isinstance(node.attr, str) and node.attr in _DANGEROUS_ATTRS:
            self.errors.append(f"禁止访问属性: {node.attr}")
        self.generic_visit(node)

    def visit_Name(self, node):
        # 检查危险内置名
        if node.id in _DANGEROUS_CALLS and isinstance(node.ctx, ast.Load):
            # 仅警告，不阻止（可能只是变量名）
            pass
        self.generic_visit(node)


def validate_strategy_code(source_code, strategy_format='auto'):
    """验证策略代码安全性

    Args:
        source_code: str, Python 源代码

    Returns:
        (bool, str): (是否安全, 错误消息)
    """
    strategy_format = strategy_format or 'auto'

    # 1. 语法检查
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        return False, f"语法错误: 第{e.lineno}行 - {e.msg}"

    # 2. 安全检查
    validator = StrategyValidator()
    validator.visit(tree)

    if validator.errors:
        return False, "安全检查失败: " + "; ".join(validator.errors[:3])

    # 3. 检查策略入口
    has_bt_strategy = False
    has_joinquant_strategy = _has_joinquant_entry(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = _get_base_name(base)
                if base_name and ('Strategy' in base_name or 'SignalStrategy' in base_name):
                    has_bt_strategy = True
                    break

    if strategy_format == 'backtrader' and not has_bt_strategy:
        return False, "Backtrader 格式需要定义 bt.Strategy 子类"

    if strategy_format == 'joinquant' and not has_joinquant_strategy:
        return False, "聚宽格式需要定义 initialize(context)，并定义 handle_data 或通过 run_daily 注册交易函数"

    if strategy_format == 'auto' and not (has_bt_strategy or has_joinquant_strategy):
        return False, "未找到 bt.Strategy 子类或聚宽 initialize/run_daily/handle_data 入口"

    return True, ""


def _get_base_name(node):
    """提取基类名称"""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return node.attr
    return None


def execute_strategy_code(source_code, filename='<uploaded>', strategy_format='auto'):
    """在受限命名空间中执行策略代码

    Args:
        source_code: str, Python 源代码
        filename: str, 文件名（用于错误提示）

    Returns:
        (strategy_class or None, error_msg or None)
    """
    # 构建受限命名空间
    safe_builtins = {
        'range': range, 'len': len, 'int': int, 'float': float,
        'str': str, 'list': list, 'dict': dict, 'tuple': tuple,
        'set': set, 'bool': bool, 'abs': abs, 'min': min, 'max': max,
        'sum': sum, 'round': round, 'sorted': sorted,
        'enumerate': enumerate, 'zip': zip, 'map': map, 'filter': filter,
        'isinstance': isinstance, 'hasattr': hasattr, 'getattr': getattr,
        'setattr': setattr, 'print': print,
        'type': type, 'object': object, 'super': super,
        'property': property, 'staticmethod': staticmethod, 'classmethod': classmethod,
        'ValueError': ValueError, 'TypeError': TypeError, 'KeyError': KeyError,
        'IndexError': IndexError, 'AttributeError': AttributeError,
        'RuntimeError': RuntimeError, 'Exception': Exception,
        'NotImplementedError': NotImplementedError,
        'True': True, 'False': False, 'None': None,
        '__import__': _safe_import,  # backtrader metaclass internals need this
        '__build_class__': __build_class__,  # Python 3 class construction
    }

    strategy_format = strategy_format or 'auto'
    source_code = _strip_joinquant_imports(source_code)

    namespace = {
        '__builtins__': safe_builtins,
        '__name__': '__main__',
        '__doc__': None,
        '__package__': None,
        '__spec__': None,
        '__loader__': None,
        '__cached__': None,
        '__file__': filename,
        'bt': bt,
        'np': np,
        'pd': pd,
        'math': math,
        'talib': _TalibFallback,
        'g': type('GlobalState', (), {})(),
        'FixedSlippage': _CompatObject,
        'OrderCost': _CompatObject,
        'set_benchmark': _noop,
        'set_option': _noop,
        'set_order_cost': _noop,
        'set_slippage': _noop,
        'run_daily': _noop,
        'order': _noop,
        'order_target': _noop,
        'order_value': _noop,
        'order_target_value': _noop,
        'order_target_percent': _noop,
        'attribute_history': _noop,
        'history': _noop,
        'get_current_data': _noop,
        'log': _UploadLogger(),
    }

    try:
        compiled = compile(source_code, filename, 'exec')
        exec(compiled, namespace)
    except Exception as e:
        return None, f"执行失败: {e}"

    # 查找 bt.Strategy 子类
    strategy_class = None
    for name, obj in namespace.items():
        if name.startswith('_'):
            continue
        try:
            if inspect.isclass(obj) and issubclass(obj, bt.Strategy) and obj is not bt.Strategy:
                strategy_class = obj
                break
        except TypeError:
            continue

    if strategy_class is not None and strategy_format in ('auto', 'backtrader'):
        return strategy_class, None

    if strategy_format in ('auto', 'joinquant'):
        if callable(namespace.get('initialize')):
            strategy_name = _strategy_name_from_filename(filename)
            return create_joinquant_strategy(namespace, strategy_name), None

    return strategy_class, None


def _has_joinquant_entry(tree):
    """判断是否为聚宽 initialize/handle_data 或 initialize/run_daily 风格策略。"""
    funcs = {
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    has_run_daily = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == 'run_daily'
        for node in ast.walk(tree)
    )
    return 'initialize' in funcs and ('handle_data' in funcs or has_run_daily)


def _strip_joinquant_imports(source_code):
    """移除本地无法导入但聚宽平台常见的 API 导入。"""
    stripped = []
    blocked_prefixes = (
        'from jqdata import',
        'import jqdata',
        'from kuanke.user_space_api import',
    )
    for line in source_code.splitlines():
        if line.strip().startswith(blocked_prefixes):
            continue
        stripped.append(line)
    return '\n'.join(stripped)


def _strategy_name_from_filename(filename):
    """从文件名生成可读策略类名。"""
    stem = (filename or 'JoinQuantStrategy').rsplit('/', 1)[-1].rsplit('.', 1)[0]
    parts = [part for part in stem.replace('-', '_').split('_') if part]
    name = ''.join(part[:1].upper() + part[1:] for part in parts)
    if not name or not name[0].isalpha():
        name = 'JoinQuantStrategy'
    return name + 'JQ'


def _noop(*args, **kwargs):
    return None


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    """受限导入，并为本地缺失的聚宽常用依赖提供轻量兜底。"""
    if name == 'talib':
        return _TalibFallback
    return __import__(name, globals, locals, fromlist, level)


class _CompatObject(SimpleNamespace):
    """兼容 FixedSlippage / OrderCost 这类聚宽配置对象。"""

    def __init__(self, *args, **kwargs):
        super().__init__(args=args, **kwargs)


class _TalibFallback:
    """TA-Lib 不存在时提供策略所需的 ATR。"""

    @staticmethod
    def ATR(high, low, close, timeperiod=14):
        high = np.asarray(high, dtype='float64')
        low = np.asarray(low, dtype='float64')
        close = np.asarray(close, dtype='float64')
        if close.size == 0:
            return np.array([], dtype='float64')

        prev_close = np.empty_like(close)
        prev_close[0] = close[0]
        prev_close[1:] = close[:-1]
        true_range = np.maximum.reduce([
            high - low,
            np.abs(high - prev_close),
            np.abs(low - prev_close),
        ])

        window = max(1, int(timeperiod or 1))
        valid = np.isfinite(true_range)
        values = np.where(valid, true_range, 0.0)
        counts = np.cumsum(valid.astype('float64'))
        sums = np.cumsum(values)
        if true_range.size > window:
            sums[window:] -= sums[:-window]
            counts[window:] -= counts[:-window]

        out = np.divide(
            sums,
            counts,
            out=np.full_like(sums, np.nan, dtype='float64'),
            where=counts > 0,
        )
        return out


class _UploadLogger:
    def info(self, *args, **kwargs):
        return None

    warn = info
    error = info
    debug = info

    def set_level(self, *args, **kwargs):
        return None
