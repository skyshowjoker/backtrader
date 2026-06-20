"""回测运行引擎 - 构建 Cerebro、运行回测、异步执行

提供同步和异步两种回测执行方式：
- run_backtest(): 同步执行，直接返回结果
- start_backtest() / check_result(): 异步执行，后台线程 + 轮询
"""

import contextlib
import io
import os
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import backtrader as bt
import pandas as pd

from .data_fetcher import download_data, ETF_POOL, BENCHMARK_POOL
from .result_extractor import build_partial_result, extract_all

_BENCHMARK_PROXY = {
    '000300': '510300',
    '000016': '510050',
    '000905': '510500',
}


class PandasDataFeed(bt.feeds.PandasData):
    """通用 Pandas 数据源，适配 akshare 数据格式"""
    params = (
        ('datetime', None),
        ('open', 'open'),
        ('high', 'high'),
        ('low', 'low'),
        ('close', 'close'),
        ('volume', 'volume'),
        ('openinterest', -1),
    )


# ==================== 异步执行状态 ====================
_results_store = {}  # task_id -> {'status': 'running'|'done'|'error', 'data': ..., 'message': ...}
_results_lock = threading.Lock()


def run_backtest(strategy_class, strategy_params, config, progress_callback=None):
    """同步执行回测

    Args:
        strategy_class: bt.Strategy 子类
        strategy_params: dict, 策略参数
        config: dict, 回测配置:
            - start_date: str 'YYYY-MM-DD'
            - end_date: str 'YYYY-MM-DD'
            - initial_cash: float
            - commission: float
            - benchmark: str 基准代码（如 '000300'）
            - data_codes: list[str] 数据代码列表
            - data_type: str 数据类型 'etf'|'index'|'stock'

    Returns:
        dict, 提取的结构化结果（来自 result_extractor）
    """
    start_date = config.get('start_date', '2020-01-01')
    end_date = config.get('end_date', '2025-12-31')
    initial_cash = config.get('initial_cash', 1000000.0)
    commission = config.get('commission', 0.0002)
    benchmark_code = config.get('benchmark', '000300')
    data_codes = config.get('data_codes', [])
    data_type = config.get('data_type', 'etf')
    requested_data_codes = list(data_codes)
    preferred_data_codes = getattr(strategy_class, '_preferred_data_codes', []) or []
    if preferred_data_codes:
        data_codes = _merge_codes(preferred_data_codes, data_codes)

    # 日期格式转换
    start_str = start_date.replace('-', '')
    end_str = end_date.replace('-', '')

    # 1. 并发下载数据
    data_feeds = _download_data_feeds(
        data_codes, start_str, end_str, data_type, progress_callback)

    if not data_feeds:
        raise ValueError("无法下载任何数据，请检查代码和日期范围")

    # 2. 下载基准数据
    benchmark_df = download_data(benchmark_code, start_str, end_str, data_type='index')
    benchmark_name = benchmark_code
    benchmark_source = 'index'

    if benchmark_df is None or len(benchmark_df) <= 20:
        proxy_code = _BENCHMARK_PROXY.get(benchmark_code)
        if proxy_code and proxy_code in data_feeds:
            benchmark_df = data_feeds[proxy_code]
            benchmark_source = f'proxy:{proxy_code}'

    if progress_callback:
        progress_callback(
            build_partial_result(data_feeds=data_feeds,
                                 benchmark_df=benchmark_df,
                                 benchmark_name=benchmark_name),
            '行情和基准已加载，正在运行回测',
        )

    data_coverage = _build_data_coverage(data_feeds)
    data_feeds, benchmark_df = _align_to_master_calendar(
        data_feeds, benchmark_df, start_date, end_date)

    benchmark_progress = _benchmark_progress_series(benchmark_df)

    # 3. 创建 Cerebro
    cerebro = bt.Cerebro(tradehistory=True, stdstats=False)

    # 添加数据源
    for code, df in data_feeds.items():
        feed = PandasDataFeed(dataname=df, name=code)
        _attach_fast_history(feed, df)
        cerebro.adddata(feed, name=code)

    # 添加基准数据（作为额外数据源，不影响策略逻辑）
    if benchmark_df is not None and len(benchmark_df) > 20:
        benchmark_feed = PandasDataFeed(dataname=benchmark_df, name=benchmark_code)
        _attach_fast_history(benchmark_feed, benchmark_df)
        cerebro.adddata(benchmark_feed, name=benchmark_code)

    # 添加策略
    cerebro.addstrategy(strategy_class, **strategy_params)

    # 设置资金
    cerebro.broker.setcash(initial_cash)

    # 设置佣金
    cerebro.broker.setcommission(commission=commission)

    # 4. 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe',
                        riskfreerate=0.02, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='time_return',
                        timeframe=bt.TimeFrame.Days)

    # 添加基准收益率分析器（跟踪基准数据的日收益率）
    if benchmark_df is not None and len(benchmark_df) > 20:
        cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='benchmark_return',
                            timeframe=bt.TimeFrame.Days, data=benchmark_feed)

    if progress_callback:
        cerebro.addanalyzer(
            _RealtimeProgressAnalyzer,
            _name='realtime_progress',
            progress_callback=progress_callback,
            initial_cash=initial_cash,
            benchmark_progress=benchmark_progress,
            emit_every_bars=10,
            emit_every_seconds=2.5,
        )

    # 5. 运行回测，并捕获策略 print / log 输出
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        results = cerebro.run()
    strat = results[0]

    # 6. 提取结果
    result = extract_all(strat, data_feeds, benchmark_name=benchmark_name)

    # 补充最终资产信息
    result['final_value'] = cerebro.broker.getvalue()
    result['initial_cash'] = initial_cash
    result['benchmark_source'] = benchmark_source
    result['loaded_data_codes'] = list(data_feeds.keys())
    result['requested_data_codes'] = requested_data_codes
    result['requested_start_date'] = start_date
    result['requested_end_date'] = end_date
    result['data_coverage'] = data_coverage
    result['logs'] = _merge_logs(
        getattr(strat, '_jq_logs', []),
        stdout.getvalue(),
        stderr.getvalue(),
    )

    return result


def _download_data_feeds(data_codes, start_str, end_str, data_type, progress_callback=None):
    """Download all securities concurrently and emit lightweight progress."""
    data_feeds = {}
    total = len(data_codes)
    if not total:
        return data_feeds

    max_workers = min(8, max(1, total))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(download_data, code, start_str, end_str, data_type=data_type): code
            for code in data_codes
        }
        for future in as_completed(futures):
            code = futures[future]
            try:
                df = future.result()
            except Exception as exc:
                print(f"[download fail] {code}: {exc}")
                df = None

            if df is not None and len(df) > 20:
                data_feeds[code] = df

            if progress_callback:
                progress_callback(
                    {
                        'partial': True,
                        'progress': {
                            'stage': 'loading',
                            'loaded': len(data_feeds),
                            'total': total,
                        },
                    },
                    f'已加载 {len(data_feeds)}/{total} 个标的',
                )

    return {
        code: data_feeds[code]
        for code in data_codes
        if code in data_feeds
    }


class _RealtimeProgressAnalyzer(bt.Analyzer):
    """Emit broker equity during Cerebro run without waiting for final analyzers."""

    params = (
        ('progress_callback', None),
        ('initial_cash', 1.0),
        ('benchmark_progress', None),
        ('emit_every_bars', 5),
        ('emit_every_seconds', 0.7),
    )

    def start(self):
        self._dates = []
        self._nav_values = []
        self._bar_count = 0
        self._started_at = time.time()
        self._last_emit_at = 0.0
        self._benchmark_progress = self.p.benchmark_progress or {}

    def next(self):
        callback = self.p.progress_callback
        if not callback:
            return

        self._bar_count += 1
        current_date = self.strategy.datas[0].datetime.date(0).strftime('%Y-%m-%d')
        broker_value = float(self.strategy.broker.getvalue())
        initial_cash = float(self.p.initial_cash or 1.0)
        nav = broker_value / initial_cash if initial_cash else 1.0

        if not self._dates or self._dates[-1] != current_date:
            self._dates.append(current_date)
            self._nav_values.append(round(nav, 8))
        else:
            self._nav_values[-1] = round(nav, 8)

        now = time.time()
        if (
            self._bar_count % int(self.p.emit_every_bars or 1) != 0
            and now - self._last_emit_at < float(self.p.emit_every_seconds or 0)
        ):
            return

        self._last_emit_at = now
        callback(
            self._build_payload(current_date, broker_value, now - self._started_at),
            f'回测运行中：{current_date}',
        )

    def stop(self):
        callback = self.p.progress_callback
        if callback and self._dates:
            current_date = self._dates[-1]
            callback(
                self._build_payload(
                    current_date,
                    float(self.strategy.broker.getvalue()),
                    time.time() - self._started_at,
                ),
                f'回测运行中：{current_date}',
            )

    def _build_payload(self, current_date, broker_value, elapsed_seconds):
        strategy_returns = [
            round((value - 1.0) * 100, 4)
            for value in self._nav_values
        ]
        benchmark_dates, benchmark_values, benchmark_returns = _slice_benchmark_progress(
            self._benchmark_progress, current_date)
        excess_dates, excess_values = _partial_excess_returns(
            self._dates, self._nav_values, benchmark_dates, benchmark_values)
        total_return = strategy_returns[-1] if strategy_returns else 0.0

        return {
            'partial': True,
            'progress': {
                'stage': 'running',
                'bars': self._bar_count,
                'current_date': current_date,
                'elapsed_seconds': round(float(elapsed_seconds), 2),
            },
            'nav_dates': list(self._dates),
            'nav_values': list(self._nav_values),
            'strategy_return_dates': list(self._dates),
            'strategy_return_values': strategy_returns,
            'benchmark_dates': benchmark_dates,
            'benchmark_values': benchmark_values,
            'benchmark_return_dates': benchmark_dates,
            'benchmark_return_values': benchmark_returns,
            'excess_return_dates': excess_dates,
            'excess_return_values': excess_values,
            'metrics': {
                'total_return': total_return,
            },
            'final_value': round(float(broker_value), 4),
        }


def _benchmark_progress_series(benchmark_df):
    if benchmark_df is None or benchmark_df.empty or 'close' not in benchmark_df:
        return {'dates': [], 'values': [], 'returns': []}

    close = pd.to_numeric(benchmark_df['close'], errors='coerce').dropna()
    if close.empty:
        return {'dates': [], 'values': [], 'returns': []}

    first = float(close.iloc[0])
    if not first:
        return {'dates': [], 'values': [], 'returns': []}

    values = [round(float(value) / first, 8) for value in close.tolist()]
    return {
        'dates': [idx.strftime('%Y-%m-%d') for idx in close.index],
        'values': values,
        'returns': [round((value - 1.0) * 100, 4) for value in values],
    }


def _slice_benchmark_progress(progress, current_date):
    dates = progress.get('dates') or []
    values = progress.get('values') or []
    returns = progress.get('returns') or []
    if not dates:
        return [], [], []

    end = 0
    for index, date in enumerate(dates):
        if date <= current_date:
            end = index + 1
        else:
            break
    return dates[:end], values[:end], returns[:end]


def _partial_excess_returns(nav_dates, nav_values, bench_dates, bench_values):
    if not nav_dates or not nav_values or not bench_dates or not bench_values:
        return [], []

    strategy = dict(zip(nav_dates, nav_values))
    benchmark = dict(zip(bench_dates, bench_values))
    dates = [date for date in nav_dates if date in benchmark]
    values = []
    for date in dates:
        bench = benchmark.get(date)
        if not bench:
            values.append(None)
        else:
            values.append(round((strategy[date] / bench - 1.0) * 100, 4))
    return dates, values


def _attach_fast_history(feed, df):
    """Attach numpy arrays used by the JoinQuant adapter's history API."""
    if df is None or df.empty:
        return
    try:
        feed._bt_dates = [idx.date() for idx in df.index]
        feed._bt_date_to_pos = {date: index for index, date in enumerate(feed._bt_dates)}
        feed._bt_arrays = {
            col: pd.to_numeric(df[col], errors='coerce').to_numpy(dtype='float64')
            for col in ['open', 'high', 'low', 'close', 'volume']
            if col in df
        }
    except Exception as exc:
        print(f"[fast history attach fail] {getattr(feed, '_name', '')}: {exc}")


def _merge_codes(primary, secondary):
    """Merge security code lists while preserving order and normalizing suffixes."""
    merged = []
    for code in list(primary or []) + list(secondary or []):
        normalized = _normalize_code(code)
        if normalized and normalized not in merged:
            merged.append(normalized)
    return merged


def _normalize_code(code):
    text = str(code or '')
    for token in text.replace(',', ' ').split():
        digits = ''.join(ch for ch in token if ch.isdigit())
        if len(digits) >= 6:
            return digits[:6]
    digits = ''.join(ch for ch in text if ch.isdigit())
    return digits[:6] if len(digits) >= 6 else ''


def _align_to_master_calendar(data_feeds, benchmark_df, start_date, end_date):
    """Pad all feeds to one calendar so late-listed ETFs do not delay the run.

    Backtrader starts strategy iteration after every data feed has delivered
    bars.  ETF pools often include funds listed after the requested start date,
    which can otherwise push a 2020 backtest to 2023.  Padding with NaN before
    first listing keeps the global clock at the requested period while the
    JoinQuant adapter treats unavailable securities as paused.
    """
    calendar = None
    if benchmark_df is not None and not benchmark_df.empty:
        calendar = pd.DatetimeIndex(benchmark_df.index)
    else:
        dates = []
        for df in data_feeds.values():
            if df is not None and not df.empty:
                dates.extend(df.index)
        if dates:
            calendar = pd.DatetimeIndex(sorted(set(dates)))

    if calendar is None or calendar.empty:
        return data_feeds, benchmark_df

    start_ts = pd.to_datetime(start_date)
    end_ts = pd.to_datetime(end_date)
    calendar = calendar[(calendar >= start_ts) & (calendar <= end_ts)]
    if calendar.empty:
        return data_feeds, benchmark_df

    aligned = {
        code: _align_ohlcv(df, calendar)
        for code, df in data_feeds.items()
        if df is not None and not df.empty
    }
    aligned_benchmark = (
        _align_ohlcv(benchmark_df, calendar)
        if benchmark_df is not None and not benchmark_df.empty
        else benchmark_df
    )
    return aligned, aligned_benchmark


def _align_ohlcv(df, calendar):
    aligned = df.reindex(calendar).copy()
    for col in ['open', 'high', 'low', 'close']:
        if col in aligned:
            aligned[col] = pd.to_numeric(aligned[col], errors='coerce').ffill()
    if 'volume' in aligned:
        aligned['volume'] = pd.to_numeric(aligned['volume'], errors='coerce').fillna(0)
    return aligned


def _build_data_coverage(data_feeds):
    coverage = []
    for code, df in data_feeds.items():
        if df is None or df.empty:
            coverage.append({'code': code, 'start': '', 'end': '', 'rows': 0})
            continue
        coverage.append({
            'code': code,
            'start': df.index[0].strftime('%Y-%m-%d'),
            'end': df.index[-1].strftime('%Y-%m-%d'),
            'rows': len(df),
        })
    return coverage


def _merge_logs(jq_logs, stdout_text, stderr_text):
    logs = []
    seen = set()

    def add(level, message, date=''):
        text = str(message or '').strip()
        if not text:
            return
        key = (date, level, text)
        if key in seen:
            return
        seen.add(key)
        logs.append({'date': date, 'level': level, 'message': text})

    for item in jq_logs or []:
        if isinstance(item, dict):
            add(item.get('level') or 'info', item.get('message'), item.get('date') or '')
        else:
            add('info', item)

    for line in str(stdout_text or '').splitlines():
        add('info', line)
    for line in str(stderr_text or '').splitlines():
        add('error', line)

    return logs[-3000:]


# ==================== 异步执行 ====================

def start_backtest(strategy_class, strategy_params, config):
    """异步启动回测（后台线程）

    Args:
        strategy_class: bt.Strategy 子类
        strategy_params: dict, 策略参数
        config: dict, 回测配置

    Returns:
        str, task_id 用于轮询结果
    """
    task_id = str(uuid.uuid4())[:8]
    started_at = time.time()
    with _results_lock:
        _results_store[task_id] = {
            'status': 'running',
            'data': None,
            'message': '准备加载行情数据',
            'started_at': started_at,
            'updated_at': started_at,
            'progress': {
                'stage': 'queued',
                'elapsed_seconds': 0,
            },
        }

    def _progress(data, message):
        now = time.time()
        progress = dict((data or {}).get('progress') or {})
        progress.setdefault('stage', 'running' if data and data.get('nav_dates') else 'loading')
        progress['elapsed_seconds'] = round(now - started_at, 2)
        if data is not None:
            data = dict(data)
            data['progress'] = progress

        with _results_lock:
            _results_store[task_id] = {
                'status': 'running',
                'data': data,
                'message': message,
                'started_at': started_at,
                'updated_at': now,
                'progress': progress,
            }

    def _run():
        try:
            result = run_backtest(strategy_class, strategy_params, config,
                                  progress_callback=_progress)
            now = time.time()
            result['runtime_seconds'] = round(now - started_at, 2)
            result['partial'] = False
            progress = {
                'stage': 'done',
                'elapsed_seconds': round(now - started_at, 2),
            }
            with _results_lock:
                _results_store[task_id] = {
                    'status': 'done',
                    'data': result,
                    'message': '回测完成',
                    'started_at': started_at,
                    'updated_at': now,
                    'progress': progress,
                }
        except Exception as e:
            now = time.time()
            with _results_lock:
                _results_store[task_id] = {
                    'status': 'error',
                    'data': str(e),
                    'message': '回测失败',
                    'started_at': started_at,
                    'updated_at': now,
                    'progress': {
                        'stage': 'error',
                        'elapsed_seconds': round(now - started_at, 2),
                    },
                }

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return task_id


def check_result(task_id):
    """检查异步回测结果

    Args:
        task_id: str, start_backtest 返回的任务 ID

    Returns:
        dict, {'status': 'running'|'done'|'error', 'data': ...}
    """
    with _results_lock:
        result = dict(_results_store.get(task_id, {
            'status': 'unknown',
            'data': None,
            'message': '未找到回测任务',
        }))

    if result.get('status') == 'running':
        started_at = result.get('started_at') or time.time()
        progress = dict(result.get('progress') or {})
        progress['elapsed_seconds'] = round(time.time() - started_at, 2)
        result['progress'] = progress
        if isinstance(result.get('data'), dict):
            data = dict(result['data'])
            data['progress'] = progress
            result['data'] = data

    return result


def clear_results():
    """清空所有回测结果"""
    with _results_lock:
        _results_store.clear()
