"""
Backtrader 数据加载器 - 支持 Tushare Parquet 格式
用于加载 /Users/mac/Downloads/行情数据 中的数据
"""

import os
import pandas as pd
import backtrader as bt
from datetime import datetime, timedelta


class TushareParquetData(bt.feeds.PandasData):
    """
    自定义数据源类,用于加载 Tushare Parquet 格式的数据

    数据特征:
    - 日线数据: stock_daily.parquet (多股票合并)
    - 分钟线数据: stock_15min/000001.SZ.parquet (单股票文件)
    - 包含复权因子 adj_factor
    - MultiIndex 索引 (trade_date, trade_time/ts_code)
    """

    # 定义数据线
    lines = ('adj_factor',)

    # 参数映射
    params = (
        ('datetime', None),  # 由 fromdate/todate 控制
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'vol'),
        ('openinterest', -1),  # 不使用
        ('adj_factor', 'adj_factor'),  # 复权因子
    )


class TushareDataLoader:
    """Tushare 数据加载器"""

    def __init__(self, data_path='/Users/mac/Downloads/行情数据'):
        """
        初始化数据加载器

        Args:
            data_path: 数据文件夹路径
        """
        self.data_path = data_path
        self.daily_file = os.path.join(data_path, 'stock_daily.parquet')

    def load_daily_data(self, ts_code, start_date=None, end_date=None,
                       adj_type='hfq', preload=True):
        """
        加载日线数据

        Args:
            ts_code: 股票代码,如 '000001.SZ'
            start_date: 开始日期,str或datetime,如 '20200101' 或 datetime(2020,1,1)
            end_date: 结束日期
            adj_type: 复权类型,'hfq'(后复权),'qfq'(前复权),'none'(不复权)
            preload: 是否预加载整个文件

        Returns:
            PandasData 对象
        """
        # 读取数据
        if preload:
            df = pd.read_parquet(self.daily_file)
        else:
            # 如果内存不够,可以分块读取
            df = pd.read_parquet(self.daily_file)

        # 筛选指定股票
        df = df.xs(ts_code, level='ts_code')

        # 处理日期
        df = df.reset_index()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df.set_index('trade_date', inplace=True)
        df.sort_index(inplace=True)

        # 日期范围筛选
        if start_date:
            if isinstance(start_date, str):
                start_date = pd.to_datetime(start_date)
            df = df[df.index >= start_date]

        if end_date:
            if isinstance(end_date, str):
                end_date = pd.to_datetime(end_date)
            df = df[df.index <= end_date]

        # 复权处理
        if adj_type == 'hfq':
            # 后复权
            df['open'] = df['open'] * df['adj_factor']
            df['high'] = df['high'] * df['adj_factor']
            df['low'] = df['low'] * df['adj_factor']
            df['close'] = df['close'] * df['adj_factor']
        elif adj_type == 'qfq':
            # 前复权 - 需要最新的复权因子
            latest_adj = df['adj_factor'].iloc[-1]
            df['open'] = df['open'] * df['adj_factor'] / latest_adj
            df['high'] = df['high'] * df['adj_factor'] / latest_adj
            df['low'] = df['low'] * df['adj_factor'] / latest_adj
            df['close'] = df['close'] * df['adj_factor'] / latest_adj

        print(f"加载数据: {ts_code}, 时间范围: {df.index[0]} 至 {df.index[-1]}, 共 {len(df)} 条")

        # 创建 Backtrader 数据源
        data = TushareParquetData(
            dataname=df,
            fromdate=start_date if start_date else df.index[0],
            todate=end_date if end_date else df.index[-1],
        )

        return data

    def load_minute_data(self, ts_code, freq='15min', start_date=None,
                        end_date=None, adj_type='hfq'):
        """
        加载分钟线数据

        Args:
            ts_code: 股票代码
            freq: 频率,'1min','15min','30min','60min'
            start_date: 开始日期
            end_date: 结束日期
            adj_type: 复权类型

        Returns:
            PandasData 对象
        """
        # 确定文件夹
        folder_map = {
            '1min': 'stock_1min',
            '15min': 'stock_15min',
            '30min': 'stock_30min',
            '60min': 'stock_60min'
        }
        folder = folder_map.get(freq)
        if not folder:
            raise ValueError(f"不支持的时间周期: {freq}")

        # 读取文件
        file_path = os.path.join(self.data_path, folder, f'{ts_code}.parquet')
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"数据文件不存在: {file_path}")

        df = pd.read_parquet(file_path)

        # 处理索引
        df = df.reset_index()

        # 使用 trade_time 作为 datetime (它已经是完整的 datetime)
        if 'trade_time' in df.columns:
            df['datetime'] = pd.to_datetime(df['trade_time'])
        else:
            df['datetime'] = pd.to_datetime(df['trade_date'])

        df.set_index('datetime', inplace=True)
        df.sort_index(inplace=True)

        # 日期筛选
        if start_date:
            if isinstance(start_date, str):
                start_date = pd.to_datetime(start_date)
            df = df[df.index >= start_date]

        if end_date:
            if isinstance(end_date, str):
                end_date = pd.to_datetime(end_date)
            df = df[df.index <= end_date]

        # 复权处理
        if adj_type == 'hfq':
            df['open'] = df['open'] * df['adj_factor']
            df['high'] = df['high'] * df['adj_factor']
            df['low'] = df['low'] * df['adj_factor']
            df['close'] = df['close'] * df['adj_factor']
        elif adj_type == 'qfq':
            latest_adj = df['adj_factor'].iloc[-1]
            df['open'] = df['open'] * df['adj_factor'] / latest_adj
            df['high'] = df['high'] * df['adj_factor'] / latest_adj
            df['low'] = df['low'] * df['adj_factor'] / latest_adj
            df['close'] = df['close'] * df['adj_factor'] / latest_adj

        print(f"加载数据: {ts_code} ({freq}), 时间范围: {df.index[0]} 至 {df.index[-1]}, 共 {len(df)} 条")

        # 创建数据源
        data = TushareParquetData(
            dataname=df,
            fromdate=start_date if start_date else df.index[0],
            todate=end_date if end_date else df.index[-1],
        )

        return data

    def load_multiple_stocks(self, ts_codes, freq='daily', start_date=None,
                            end_date=None, adj_type='hfq'):
        """
        加载多只股票数据

        Args:
            ts_codes: 股票代码列表
            freq: 频率
            start_date: 开始日期
            end_date: 结束日期
            adj_type: 复权类型

        Returns:
            数据源列表
        """
        datas = []
        for ts_code in ts_codes:
            if freq == 'daily':
                data = self.load_daily_data(ts_code, start_date, end_date, adj_type)
            else:
                data = self.load_minute_data(ts_code, freq, start_date, end_date, adj_type)
            datas.append(data)
        return datas


def create_data_feed_example():
    """创建数据源的示例代码"""

    # 方式1: 使用加载器
    loader = TushareDataLoader('/Users/mac/Downloads/行情数据')

    # 加载日线数据
    data_daily = loader.load_daily_data(
        ts_code='000001.SZ',
        start_date='2020-01-01',
        end_date='2023-12-31',
        adj_type='hfq'
    )

    # 加载分钟线数据
    data_15min = loader.load_minute_data(
        ts_code='000001.SZ',
        freq='15min',
        start_date='2023-01-01',
        adj_type='qfq'
    )

    return data_daily, data_15min


if __name__ == '__main__':
    # 测试数据加载
    print("=" * 60)
    print("测试数据加载")
    print("=" * 60)

    loader = TushareDataLoader()

    # 测试日线数据
    print("\n1. 测试日线数据加载")
    data = loader.load_daily_data('000001.SZ', '2023-01-01', '2023-12-31')
    print(f"数据类型: {type(data)}")

    # 测试分钟线数据
    print("\n2. 测试15分钟线数据加载")
    data_15 = loader.load_minute_data('000001.SZ', '15min', '2023-06-01', '2023-06-30')
    print(f"数据类型: {type(data_15)}")

    print("\n数据加载测试完成!")
