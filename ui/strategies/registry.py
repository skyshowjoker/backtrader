"""策略注册表 - 管理所有可用策略

提供统一的策略注册/查询接口，支持内置策略和运行时动态添加的自定义策略。
每个注册条目包含：策略类、参数 schema、描述信息。
"""


class StrategyRegistry:
    """策略注册表（单例模式）"""

    _instance = None
    _strategies = {}  # name -> {class, params, description, category}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, name, strategy_class, description='', category='builtin'):
        """注册策略

        Args:
            name: str, 策略显示名称
            strategy_class: bt.Strategy 子类
            description: str, 策略描述
            category: str, 'builtin' | 'custom'
        """
        params_schema = cls._extract_params(strategy_class)
        cls._strategies[name] = {
            'class': strategy_class,
            'params': params_schema,
            'description': description,
            'category': category,
        }

    @classmethod
    def get(cls, name):
        """获取策略信息

        Returns:
            dict or None
        """
        return cls._strategies.get(name)

    @classmethod
    def get_class(cls, name):
        """获取策略类

        Returns:
            bt.Strategy 子类 or None
        """
        info = cls._strategies.get(name)
        return info['class'] if info else None

    @classmethod
    def get_params(cls, name):
        """获取策略参数 schema

        Returns:
            list[dict] 参数列表，每个 dict 含 name, type, default, label
        """
        info = cls._strategies.get(name)
        return info.get('params', []) if info else []

    @classmethod
    def list_all(cls):
        """列出所有策略名称"""
        return list(cls._strategies.keys())

    @classmethod
    def list_builtin(cls):
        """列出内置策略"""
        return [k for k, v in cls._strategies.items() if v['category'] == 'builtin']

    @classmethod
    def list_custom(cls):
        """列出自定义策略"""
        return [k for k, v in cls._strategies.items() if v['category'] == 'custom']

    @classmethod
    def get_dropdown_options(cls):
        """获取 Dash Dropdown 选项格式"""
        options = []
        # 内置策略
        builtin = [k for k, v in cls._strategies.items() if v['category'] == 'builtin']
        if builtin:
            options.append({'label': '── 内置策略 ──', 'value': '', 'disabled': True})
            for name in builtin:
                desc = cls._strategies[name]['description']
                label = f"{name}" + (f" - {desc[:20]}" if desc else '')
                options.append({'label': label, 'value': name})

        # 自定义策略
        custom = [k for k, v in cls._strategies.items() if v['category'] == 'custom']
        if custom:
            options.append({'label': '── 自定义策略 ──', 'value': '', 'disabled': True})
            for name in custom:
                options.append({'label': f"📎 {name}", 'value': name})

        return options

    @classmethod
    def _extract_params(cls, strategy_class):
        """从策略类提取参数 schema

        将 bt.Strategy 的 params 元组转换为 UI 可用的参数描述列表。
        """
        params_schema = []

        if not hasattr(strategy_class, 'params') or strategy_class.params is None:
            return params_schema

        # 遍历策略参数（排除以 _ 开头的内部参数）
        for pname in strategy_class.params._getkeys():
            if pname.startswith('_'):
                continue

            default = getattr(strategy_class.params, pname, None)

            # 推断参数类型
            if isinstance(default, bool):
                ptype = 'bool'
            elif isinstance(default, int):
                ptype = 'int'
            elif isinstance(default, float):
                ptype = 'float'
            elif isinstance(default, str):
                ptype = 'str'
            else:
                ptype = 'str'

            # 生成中文标签（简单映射）
            label = _param_label_map.get(pname, pname)

            params_schema.append({
                'name': pname,
                'type': ptype,
                'default': default,
                'label': label,
            })

        return params_schema

    @classmethod
    def unregister(cls, name):
        """移除策略（仅限自定义策略）"""
        info = cls._strategies.get(name)
        if info and info['category'] == 'custom':
            del cls._strategies[name]


# 参数名 → 中文标签映射
_param_label_map = {
    'period': '周期',
    'period1': '短期均线周期',
    'period2': '长期均线周期',
    'fast_period': '快线周期',
    'slow_period': '慢线周期',
    'target_num': '持有数量',
    'auto_lookback': '动态回看期',
    'fixed_lookback': '固定回看期',
    'min_lookback': '最小回看期',
    'max_lookback': '最大回看期',
    'printlog': '打印日志',
    'stake': '单笔数量',
    'stop_loss': '止损比例',
    'take_profit': '止盈比例',
    'trail': '追踪止损',
}
