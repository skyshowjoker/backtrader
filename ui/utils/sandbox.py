"""自定义策略安全执行模块

提供 AST 级别的安全检查和受限命名空间执行。
适用于本地/个人使用场景，非加密级安全。
"""

import ast
import inspect

import backtrader as bt
import numpy as np
import pandas as pd


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


def validate_strategy_code(source_code):
    """验证策略代码安全性

    Args:
        source_code: str, Python 源代码

    Returns:
        (bool, str): (是否安全, 错误消息)
    """
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

    # 3. 检查是否包含 bt.Strategy 子类
    has_strategy = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = _get_base_name(base)
                if base_name and ('Strategy' in base_name or 'SignalStrategy' in base_name):
                    has_strategy = True
                    break

    if not has_strategy:
        return False, "代码中未找到 bt.Strategy 子类定义"

    return True, ""


def _get_base_name(node):
    """提取基类名称"""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return node.attr
    return None


def execute_strategy_code(source_code, filename='<uploaded>'):
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
        '__import__': __import__,  # backtrader metaclass internals need this
        '__build_class__': __build_class__,  # Python 3 class construction
    }

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

    return strategy_class, None
