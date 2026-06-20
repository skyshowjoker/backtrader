"""Register local JoinQuant-format strategies as built-ins."""

import ast
from pathlib import Path

from ui.strategies.registry import StrategyRegistry
from ui.utils.sandbox import execute_strategy_code, validate_strategy_code


JOINQUANT_ETF_STRATEGY_NAME = 'ETF轮动最终优化（聚宽）'


def register_joinquant_etf_strategy():
    """Register strategies/etf/etf.py without modifying the strategy source."""
    source_path = Path(__file__).resolve().parents[2] / 'strategies' / 'etf' / 'etf.py'
    if not source_path.exists():
        return False

    try:
        source_code = source_path.read_text(encoding='utf-8')
    except OSError as exc:
        print(f"[builtin joinquant read fail] {source_path}: {exc}")
        return False

    valid, error_msg = validate_strategy_code(source_code, 'joinquant')
    if not valid:
        print(f"[builtin joinquant validate fail] {source_path}: {error_msg}")
        return False

    strategy_class, exec_error = execute_strategy_code(
        source_code, source_path.name, 'joinquant')
    if exec_error or strategy_class is None:
        print(f"[builtin joinquant execute fail] {source_path}: {exec_error or 'no strategy class'}")
        return False

    strategy_class._preferred_data_codes = _extract_etf_pool_codes(source_code)
    strategy_class._source_path = str(source_path)
    strategy_class._strategy_format = 'joinquant'

    StrategyRegistry.register(
        name=JOINQUANT_ETF_STRATEGY_NAME,
        strategy_class=strategy_class,
        description='内置 strategies/etf/etf.py 聚宽ETF轮动策略',
        category='builtin',
    )
    return True


def _extract_etf_pool_codes(source_code):
    """Extract g.etf_pool codes from JoinQuant source without executing it."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return []

    codes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(_is_g_etf_pool(target) for target in node.targets):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            continue

        for item in node.value.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                code = item.value.split('.', 1)[0]
                if code.isdigit() and len(code) == 6 and code not in codes:
                    codes.append(code)

    return codes


def _is_g_etf_pool(node):
    return (
        isinstance(node, ast.Attribute)
        and node.attr == 'etf_pool'
        and isinstance(node.value, ast.Name)
        and node.value.id == 'g'
    )
