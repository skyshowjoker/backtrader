"""数据获取模块 - 封装 akshare 数据下载逻辑

复用 strategies/etf/etf_backtest.py 中的下载逻辑，
提供统一的 ETF/股票历史数据获取接口，带内存缓存。
"""

import os
from pathlib import Path
import pandas as pd
import akshare as ak

# 禁用系统代理，避免 akshare 请求被拦截
for _proxy_key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(_proxy_key, None)
os.environ['NO_PROXY'] = '*'

# 内存缓存：key = (code, start_date, end_date), value = DataFrame
_cache = {}
_CACHE_DIR = Path(os.environ.get(
    'BACKTRADER_DATA_CACHE',
    Path(__file__).resolve().parents[2] / '.cache' / 'market_data',
))

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
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

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
            market = _infer_market(code, data_type='etf')
            df = _download_from_qq(code, start_date, end_date, market=market)
        except Exception as e:
            print(f"[FAIL] {code} all sources failed: {e}")

    if df is not None and not df.empty:
        _set_cached(cache_key, df)
    else:
        _set_cached(cache_key, _empty_frame())

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
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

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
            df = _download_from_qq(
                code, start_date, end_date,
                market=_infer_market(code, data_type='index'),
            )
        except Exception as e:
            print(f"[qq index fail] {code}: {e}")

    if df is not None and not df.empty:
        _set_cached(cache_key, df)
    else:
        _set_cached(cache_key, _empty_frame())

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
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

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
            df = _download_from_qq(
                code, start_date, end_date,
                market=_infer_market(code, data_type='stock'),
            )
        except Exception as e:
            print(f"[qq stock fail] {code}: {e}")

    if df is not None and not df.empty:
        _set_cached(cache_key, df)
    else:
        _set_cached(cache_key, _empty_frame())

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


def _get_cached(cache_key):
    if cache_key in _cache:
        return _cache[cache_key]

    path = _cache_path(cache_key)
    if path.exists():
        try:
            df = pd.read_pickle(path)
        except Exception as exc:
            print(f"[cache read fail] {path.name}: {exc}")
        else:
            if df is not None:
                _cache[cache_key] = df
                return df

    return _get_superset_cached(cache_key)


def _set_cached(cache_key, df):
    _cache[cache_key] = df
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_pickle(_cache_path(cache_key))
    except Exception as exc:
        print(f"[cache write fail] {cache_key}: {exc}")


def _cache_path(cache_key):
    name = '_'.join(str(part).replace('/', '-').replace(':', '-') for part in cache_key)
    return _CACHE_DIR / f'{name}.pkl'


def _get_superset_cached(cache_key):
    """Reuse a wider cached date range for shorter backtests."""
    symbol, start_date, end_date = cache_key
    covered_empty = False

    for cached_key, cached_df in list(_cache.items()):
        if _covers_range(cached_key, symbol, start_date, end_date):
            sliced = _slice_cached_df(cached_df, start_date, end_date)
            if sliced is not None and not sliced.empty:
                _cache[cache_key] = sliced
                return sliced
            covered_empty = True

    if not _CACHE_DIR.exists():
        return _empty_cached(cache_key) if covered_empty else None

    for path in _CACHE_DIR.glob('*.pkl'):
        cached_key = _parse_cache_stem(path.stem)
        if not cached_key or not _covers_range(cached_key, symbol, start_date, end_date):
            continue
        try:
            cached_df = pd.read_pickle(path)
        except Exception as exc:
            print(f"[cache read fail] {path.name}: {exc}")
            continue
        sliced = _slice_cached_df(cached_df, start_date, end_date)
        if sliced is not None and not sliced.empty:
            _cache[cache_key] = sliced
            return sliced
        covered_empty = True

    return _empty_cached(cache_key) if covered_empty else None


def _empty_cached(cache_key):
    df = _empty_frame()
    _cache[cache_key] = df
    return df


def _empty_frame():
    df = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
    df.index = pd.DatetimeIndex([], name='date')
    return df


def _covers_range(cached_key, symbol, start_date, end_date):
    return (
        len(cached_key) == 3
        and cached_key[0] == symbol
        and str(cached_key[1]) <= str(start_date)
        and str(cached_key[2]) >= str(end_date)
    )


def _parse_cache_stem(stem):
    parts = str(stem).split('_')
    if len(parts) < 3:
        return None
    end_date = parts[-1]
    start_date = parts[-2]
    symbol = '_'.join(parts[:-2])
    if len(start_date) != 8 or len(end_date) != 8:
        return None
    return symbol, start_date, end_date


def _slice_cached_df(df, start_date, end_date):
    if df is None or df.empty:
        return None
    start_ts = pd.to_datetime(start_date)
    end_ts = pd.to_datetime(end_date)
    sliced = df.loc[(df.index >= start_ts) & (df.index <= end_ts)].copy()
    return sliced if not sliced.empty else None


def _infer_market(code, data_type='auto'):
    """推断腾讯接口所需市场前缀。"""
    code = str(code or '')

    if data_type == 'index':
        if code.startswith('399'):
            return 'sz'
        return 'sh'

    if data_type == 'stock':
        if code.startswith(('6', '9')):
            return 'sh'
        return 'sz'

    if code.startswith(('5', '588', '589')):
        return 'sh'
    if code.startswith(('15', '16', '18')):
        return 'sz'
    if code.startswith(('6', '9')):
        return 'sh'
    if code.startswith(('000', '001', '002', '003', '300', '301')):
        return 'sz'
    return 'sz'


def _download_from_qq(code, start_date, end_date, market=None):
    """通过腾讯财经接口下载 ETF 历史数据（兜底方案）

    Args:
        code: ETF代码（纯数字）
        start_date: 开始日期 'YYYYMMDD'
        end_date: 结束日期 'YYYYMMDD'
    """
    import requests as _requests

    market = market or ('sh' if code.startswith(('5', '6')) else 'sz')
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
