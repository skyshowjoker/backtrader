"""数据获取模块 - 封装 akshare 数据下载逻辑

复用 strategies/etf/etf_backtest.py 中的下载逻辑，
提供统一的 ETF/股票历史数据获取接口，带内存缓存。
"""

import os
import pandas as pd
import akshare as ak

# 禁用系统代理，避免 akshare 请求被拦截
for _proxy_key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(_proxy_key, None)
os.environ['NO_PROXY'] = '*'

# 内存缓存：key = (code, start_date, end_date), value = DataFrame
_cache = {}

# 常见基准指数代码
BENCHMARK_POOL = {
    "000300": "沪深300",
    "000016": "上证50",
    "000905": "中证500",
    "000852": "中证1000",
}

# ETF 代码池（复用 etf_backtest.py 的配置）
ETF_POOL = {
    "513100": "纳指ETF",
    "513520": "日经ETF",
    "513030": "德国ETF",
    "518880": "黄金ETF",
    "159980": "有色ETF",
    "159985": "豆粕ETF",
    "501018": "南方原油",
    "511090": "30年国债ETF",
    "513130": "恒生科技",
    "512890": "红利低波",
    "159915": "创业板",
    "510300": "沪深300",
}


def download_etf_data(code, start_date, end_date):
    """下载 ETF 历史数据

    优先使用 akshare（东方财富源），失败则使用腾讯接口。

    Args:
        code: ETF 代码（纯数字，如 '513100'）
        start_date: 开始日期 'YYYYMMDD'
        end_date: 结束日期 'YYYYMMDD'

    Returns:
        DataFrame with DatetimeIndex, columns: open, high, low, close, volume
        或 None（下载失败时）
    """
    cache_key = (code, start_date, end_date)
    if cache_key in _cache:
        return _cache[cache_key]

    df = None

    # 方式1: akshare (东方财富源)
    try:
        df = ak.fund_etf_hist_em(symbol=code, period="daily",
                                 start_date=start_date, end_date=end_date, adjust="qfq")
        if df is not None and not df.empty:
            df = df.rename(columns={
                '日期': 'date', '开盘': 'open', '最高': 'high',
                '最低': 'low', '收盘': 'close', '成交量': 'volume',
            })
            df = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=['close'])
    except Exception as e:
        print(f"[akshare fail] {code}: {e}")

    # 方式2: 腾讯财经接口
    if df is None or df.empty:
        try:
            df = _download_from_qq(code, start_date, end_date)
        except Exception as e:
            print(f"[FAIL] {code} all sources failed: {e}")

    if df is not None and not df.empty:
        _cache[cache_key] = df

    return df


def download_index_data(code, start_date, end_date):
    """下载指数历史数据

    Args:
        code: 指数代码（纯数字，如 '000300'）
        start_date: 开始日期 'YYYYMMDD'
        end_date: 结束日期 'YYYYMMDD'

    Returns:
        DataFrame with DatetimeIndex, columns: open, high, low, close, volume
        或 None（下载失败时）
    """
    cache_key = (f"idx_{code}", start_date, end_date)
    if cache_key in _cache:
        return _cache[cache_key]

    df = None
    try:
        df = ak.index_zh_a_hist(symbol=code, period="daily",
                                start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            df = df.rename(columns={
                '日期': 'date', '开盘': 'open', '最高': 'high',
                '最低': 'low', '收盘': 'close', '成交量': 'volume',
            })
            df = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=['close'])
    except Exception as e:
        print(f"[akshare index fail] {code}: {e}")

    # 兜底：腾讯接口（指数也支持）
    if df is None or df.empty:
        try:
            df = _download_from_qq(code, start_date, end_date)
        except Exception as e:
            print(f"[qq index fail] {code}: {e}")

    if df is not None and not df.empty:
        _cache[cache_key] = df

    return df


def download_stock_data(code, start_date, end_date):
    """下载股票历史数据

    Args:
        code: 股票代码（纯数字，如 '600519'）
        start_date: 开始日期 'YYYYMMDD'
        end_date: 结束日期 'YYYYMMDD'

    Returns:
        DataFrame with DatetimeIndex, columns: open, high, low, close, volume
        或 None（下载失败时）
    """
    cache_key = (f"stk_{code}", start_date, end_date)
    if cache_key in _cache:
        return _cache[cache_key]

    df = None
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                start_date=start_date, end_date=end_date, adjust="qfq")
        if df is not None and not df.empty:
            df = df.rename(columns={
                '日期': 'date', '开盘': 'open', '最高': 'high',
                '最低': 'low', '收盘': 'close', '成交量': 'volume',
            })
            df = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=['close'])
    except Exception as e:
        print(f"[akshare stock fail] {code}: {e}")

    # 兜底：腾讯接口
    if df is None or df.empty:
        try:
            df = _download_from_qq(code, start_date, end_date)
        except Exception as e:
            print(f"[qq stock fail] {code}: {e}")

    if df is not None and not df.empty:
        _cache[cache_key] = df

    return df


def download_data(code, start_date, end_date, data_type='auto'):
    """统一数据下载接口

    根据代码特征自动判断类型（ETF/指数/股票），或手动指定。

    Args:
        code: 代码（纯数字）
        start_date: 开始日期 'YYYYMMDD'
        end_date: 结束日期 'YYYYMMDD'
        data_type: 'auto' | 'etf' | 'index' | 'stock'

    Returns:
        DataFrame 或 None
    """
    if data_type == 'auto':
        if code in ETF_POOL or code in BENCHMARK_POOL:
            if code in BENCHMARK_POOL:
                data_type = 'index'
            else:
                data_type = 'etf'
        elif code.startswith('000') or code.startswith('399'):
            data_type = 'index'
        else:
            data_type = 'etf'  # 默认尝试 ETF

    if data_type == 'index':
        return download_index_data(code, start_date, end_date)
    elif data_type == 'etf':
        return download_etf_data(code, start_date, end_date)
    elif data_type == 'stock':
        return download_stock_data(code, start_date, end_date)
    else:
        return download_etf_data(code, start_date, end_date)


def clear_cache():
    """清空内存缓存"""
    _cache.clear()


def _download_from_qq(code, start_date, end_date):
    """通过腾讯财经接口下载 ETF 历史数据（兜底方案）

    Args:
        code: ETF代码（纯数字）
        start_date: 开始日期 'YYYYMMDD'
        end_date: 结束日期 'YYYYMMDD'
    """
    import requests as _requests

    market = 'sh' if code.startswith(('5', '6')) else 'sz'
    symbol = f"{market}{code}"

    all_data = []
    end_dt = pd.to_datetime(end_date)
    start_dt = pd.to_datetime(start_date)

    session = _requests.Session()
    session.trust_env = False

    days_diff = (end_dt - start_dt).days
    batch_size = 800
    batches = max(1, (days_diff // 250) + 1)

    current_end = end_dt.strftime('%Y-%m-%d')

    for i in range(batches + 1):
        url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
               f"?param={symbol},day,,{current_end},{batch_size},qfq")
        resp = session.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        data = resp.json()

        if data.get('code') != 0:
            break

        stock_data = data.get('data', {}).get(symbol, {})
        klines = stock_data.get('qfqday', stock_data.get('day', []))

        if not klines:
            break

        for k in klines:
            d = pd.to_datetime(k[0])
            if start_dt <= d <= end_dt:
                all_data.append({
                    'date': d,
                    'open': float(k[1]),
                    'close': float(k[2]),
                    'high': float(k[3]),
                    'low': float(k[4]),
                    'volume': float(k[5]),
                })

        earliest = pd.to_datetime(klines[0][0])
        if earliest <= start_dt:
            break
        current_end = earliest.strftime('%Y-%m-%d')

    if not all_data:
        return None

    df = pd.DataFrame(all_data)
    df = df.drop_duplicates(subset='date').set_index('date').sort_index()
    df = df.dropna(subset=['close'])

    return df
