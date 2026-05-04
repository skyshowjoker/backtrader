"""
数据浏览工具
用于查看和检查本地数据
"""

import pandas as pd
import os


class DataBrowser:
    """数据浏览器"""

    def __init__(self, data_path='/Users/mac/Downloads/行情数据'):
        self.data_path = data_path

    def show_overview(self):
        """显示数据概览"""
        print("=" * 80)
        print("数据文件夹概览")
        print("=" * 80)

        # 日线数据
        daily_file = os.path.join(self.data_path, 'stock_daily.parquet')
        if os.path.exists(daily_file):
            file_size = os.path.getsize(daily_file) / (1024**3)
            print(f"\n【日线数据】")
            print(f"  文件: stock_daily.parquet")
            print(f"  大小: {file_size:.2f} GB")

            df = pd.read_parquet(daily_file)
            stocks = df.index.get_level_values('ts_code').unique()
            print(f"  股票数: {len(stocks)} 只")
            print(f"  记录数: {len(df):,} 条")

            # 时间范围
            dates = df.index.get_level_values('trade_date')
            print(f"  时间范围: {dates.min()} 至 {dates.max()}")
            print(f"  字段数: {len(df.columns)} 个")
            print(f"  字段: {', '.join(df.columns[:10])}...")

        # 分钟线数据
        print(f"\n【分钟线数据】")
        for freq in ['1min', '15min', '30min', '60min']:
            folder = os.path.join(self.data_path, f'stock_{freq}')
            if os.path.exists(folder):
                file_count = len([f for f in os.listdir(folder) if f.endswith('.parquet')])
                print(f"  {freq:6s}: {file_count} 个文件")

    def list_stocks(self, limit=20):
        """列出所有股票"""
        print("\n" + "=" * 80)
        print(f"股票列表 (前{limit}只)")
        print("=" * 80)

        daily_file = os.path.join(self.data_path, 'stock_daily.parquet')
        df = pd.read_parquet(daily_file)
        stocks = df.index.get_level_values('ts_code').unique()

        for i, stock in enumerate(stocks[:limit]):
            print(f"  {i+1:3d}. {stock}")

        print(f"\n共 {len(stocks)} 只股票")

    def show_stock_data(self, ts_code, start_date=None, end_date=None):
        """显示指定股票的数据"""
        print("\n" + "=" * 80)
        print(f"股票数据: {ts_code}")
        print("=" * 80)

        daily_file = os.path.join(self.data_path, 'stock_daily.parquet')
        df = pd.read_parquet(daily_file)

        # 筛选股票
        try:
            stock_df = df.xs(ts_code, level='ts_code')
        except KeyError:
            print(f"未找到股票: {ts_code}")
            return

        # 日期筛选
        stock_df = stock_df.reset_index()
        stock_df['trade_date'] = pd.to_datetime(stock_df['trade_date'])
        stock_df.set_index('trade_date', inplace=True)
        stock_df.sort_index(inplace=True)

        if start_date:
            stock_df = stock_df[stock_df.index >= start_date]
        if end_date:
            stock_df = stock_df[stock_df.index <= end_date]

        print(f"\n时间范围: {stock_df.index[0]} 至 {stock_df.index[-1]}")
        print(f"记录数: {len(stock_df)} 条")

        print("\n最近5条记录:")
        print(stock_df[['open', 'high', 'low', 'close', 'vol', 'adj_factor']].tail())

        print("\n基本统计:")
        print(stock_df[['open', 'high', 'low', 'close']].describe())

    def check_minute_data(self, ts_code, freq='15min'):
        """检查分钟线数据"""
        print("\n" + "=" * 80)
        print(f"分钟线数据: {ts_code} ({freq})")
        print("=" * 80)

        file_path = os.path.join(self.data_path, f'stock_{freq}', f'{ts_code}.parquet')

        if not os.path.exists(file_path):
            print(f"文件不存在: {file_path}")
            return

        df = pd.read_parquet(file_path)

        print(f"\n时间范围: {df.index[0]} 至 {df.index[-1]}")
        print(f"记录数: {len(df)} 条")
        print(f"字段: {df.columns.tolist()}")

        print("\n最近5条记录:")
        print(df[['open', 'high', 'low', 'close', 'vol']].tail())

    def find_stock_by_name(self, keyword):
        """根据关键字搜索股票"""
        print("\n" + "=" * 80)
        print(f"搜索股票: {keyword}")
        print("=" * 80)

        basic_file = os.path.join(self.data_path, 'stock_basic_data.parquet')
        if not os.path.exists(basic_file):
            print("未找到股票基础信息文件")
            return

        df = pd.read_parquet(basic_file)

        # 搜索
        if 'name' in df.columns:
            matches = df[df['name'].str.contains(keyword, na=False)]
            if len(matches) > 0:
                print(f"\n找到 {len(matches)} 只股票:")
                print(matches[['ts_code', 'name']].head(20))
            else:
                print("未找到匹配的股票")
        else:
            print("基础信息文件中没有股票名称字段")


def main():
    """主函数"""
    browser = DataBrowser()

    # 1. 显示概览
    browser.show_overview()

    # 2. 列出股票
    browser.list_stocks(20)

    # 3. 查看具体股票数据
    browser.show_stock_data('000001.SZ', '2023-12-01', '2023-12-31')

    # 4. 检查分钟线数据
    browser.check_minute_data('000001.SZ', '15min')

    # 5. 搜索股票
    # browser.find_stock_by_name('平安')


if __name__ == '__main__':
    main()
