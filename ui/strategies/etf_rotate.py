"""ETF 动量轮动策略适配器

导入 strategies/etf/etf_backtest.py 中的 ETFRotateStrategy，
注册到 UI 策略注册表。
"""

import sys
import os

# 将项目根目录加入 sys.path，确保能导入 strategies 模块
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from ui.strategies.registry import StrategyRegistry

try:
    from strategies.etf.etf_backtest import ETFRotateStrategy
    _ETF_AVAILABLE = True
except ImportError:
    _ETF_AVAILABLE = False


def register_etf_strategy():
    """注册 ETF 轮动策略到注册表"""
    if not _ETF_AVAILABLE:
        return

    StrategyRegistry.register(
        name='ETF动量轮动',
        strategy_class=ETFRotateStrategy,
        description='基于年化收益×R²打分的ETF动量轮动策略',
        category='builtin',
    )


# 自动注册
register_etf_strategy()
