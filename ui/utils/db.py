"""SQLite 持久化存储模块

提供回测结果、任务历史、证券列表、交易日历的数据库存储。
使用 Python 内置 sqlite3，零外部依赖。
"""

import json
import sqlite3
import os
import time
from datetime import datetime
from pathlib import Path

_DB_DIR = Path(os.environ.get(
    'BACKTRADER_DB_PATH',
    Path(__file__).resolve().parents[2] / '.cache',
))
_DB_FILE = _DB_DIR / 'backquant.db'

_MAX_BACKTEST_ROWS = 100


def _now_iso():
    return datetime.now().isoformat(timespec='seconds')


def _connect():
    """获取数据库连接（每次新建，确保线程安全）"""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_FILE), timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表（CREATE TABLE IF NOT EXISTS，自动建表）"""
    conn = _connect()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS backtests (
                task_id TEXT PRIMARY KEY,
                strategy TEXT NOT NULL,
                params TEXT,
                config TEXT,
                status TEXT NOT NULL,
                message TEXT,
                summary TEXT,
                result_data TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                message TEXT,
                progress TEXT,
                partial_data TEXT,
                started_at REAL,
                updated_at REAL
            );

            CREATE TABLE IF NOT EXISTS securities_cache (
                cache_key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                fetched_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trade_days_cache (
                year INTEGER PRIMARY KEY,
                days TEXT NOT NULL,
                fetched_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_backtests_created
                ON backtests(created_at);
            CREATE INDEX IF NOT EXISTS idx_backtests_status
                ON backtests(status);
        """)
        conn.commit()
    finally:
        conn.close()


# ==================== Backtests ====================

def save_backtest(task_id, strategy, params, config, status, message,
                   summary, result_data, created_at, updated_at):
    """保存或更新回测记录"""
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")

        # If created_at is None, check if record already exists
        if created_at is None:
            existing = conn.execute(
                "SELECT created_at FROM backtests WHERE task_id=?", (task_id,)
            ).fetchone()
            created_at = existing['created_at'] if existing else _now_iso()

        if updated_at is None:
            updated_at = _now_iso()

        conn.execute(
            """INSERT OR REPLACE INTO backtests
               (task_id, strategy, params, config, status, message,
                summary, result_data, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id,
                strategy,
                json.dumps(params, ensure_ascii=False) if params else None,
                json.dumps(config, ensure_ascii=False) if config else None,
                status,
                message,
                json.dumps(summary, ensure_ascii=False) if summary else None,
                json.dumps(result_data, ensure_ascii=False) if result_data else None,
                created_at,
                updated_at,
            ),
        )
        conn.commit()
        _trim_backtests(conn)
    finally:
        conn.close()


def update_backtest_status(task_id, status, message=None, updated_at=None):
    """更新回测状态"""
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """UPDATE backtests SET status=?, message=?, updated_at=?
               WHERE task_id=?""",
            (status, message, updated_at, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def load_backtest(task_id):
    """加载单个回测记录"""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM backtests WHERE task_id=?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_backtest_dict(row)
    finally:
        conn.close()


def list_backtests(limit=50):
    """列出所有回测记录（按创建时间倒序）"""
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT task_id, strategy, params, config, status, message,
                      summary, created_at, updated_at
               FROM backtests ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [_row_to_backtest_summary(row) for row in rows]
    finally:
        conn.close()


def delete_backtest(task_id):
    """删除单个回测记录"""
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM backtests WHERE task_id=?", (task_id,))
        conn.commit()
    finally:
        conn.close()


def _trim_backtests(conn):
    """保留最新 _MAX_BACKTEST_ROWS 条记录"""
    count = conn.execute("SELECT COUNT(*) FROM backtests").fetchone()[0]
    if count <= _MAX_BACKTEST_ROWS:
        return
    conn.execute(
        """DELETE FROM backtests WHERE task_id IN (
            SELECT task_id FROM backtests ORDER BY created_at ASC
            LIMIT ?
        )""",
        (count - _MAX_BACKTEST_ROWS,),
    )


# ==================== Tasks (running state) ====================

def save_task(task_id, status, message, progress, partial_data,
              started_at, updated_at):
    """保存运行任务状态"""
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT OR REPLACE INTO tasks
               (task_id, status, message, progress, partial_data,
                started_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id,
                status,
                message,
                json.dumps(progress) if progress else None,
                json.dumps(partial_data) if partial_data else None,
                started_at,
                updated_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_task(task_id, status=None, message=None, progress=None,
                partial_data=None, updated_at=None):
    """更新运行任务状态"""
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()
        if existing is None:
            conn.commit()
            return
        conn.execute(
            """UPDATE tasks SET
               status=COALESCE(?, status),
               message=COALESCE(?, message),
               progress=COALESCE(?, progress),
               partial_data=COALESCE(?, partial_data),
               updated_at=COALESCE(?, updated_at)
               WHERE task_id=?""",
            (
                status,
                message,
                json.dumps(progress) if progress else None,
                json.dumps(partial_data) if partial_data else None,
                updated_at,
                task_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_task(task_id):
    """加载运行任务状态"""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            'task_id': row['task_id'],
            'status': row['status'],
            'message': row['message'] or '',
            'progress': json.loads(row['progress']) if row['progress'] else {},
            'partial_data': json.loads(row['partial_data']) if row['partial_data'] else None,
            'started_at': row['started_at'],
            'updated_at': row['updated_at'],
        }
    finally:
        conn.close()


def delete_task(task_id):
    """删除运行任务记录"""
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
        conn.commit()
    finally:
        conn.close()


def load_task_partial_data(task_id):
    """加载运行任务的增量数据"""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT partial_data FROM tasks WHERE task_id=?", (task_id,)
        ).fetchone()
        if row is None or row['partial_data'] is None:
            return None
        return json.loads(row['partial_data'])
    finally:
        conn.close()


# ==================== Securities Cache ====================

def save_securities_cache(cache_key, data, fetched_at=None):
    """缓存证券列表数据"""
    if fetched_at is None:
        fetched_at = time.time()
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT OR REPLACE INTO securities_cache
               (cache_key, data, fetched_at) VALUES (?, ?, ?)""",
            (cache_key, json.dumps(data, ensure_ascii=False), fetched_at),
        )
        conn.commit()
    finally:
        conn.close()


def load_securities_cache(cache_key, ttl_seconds=86400):
    """加载缓存的证券列表数据（超过 TTL 则返回 None）"""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT data, fetched_at FROM securities_cache WHERE cache_key=?",
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        if time.time() - row['fetched_at'] > ttl_seconds:
            return None
        return json.loads(row['data'])
    finally:
        conn.close()


# ==================== Trade Days Cache ====================

def save_trade_days_cache(year, days, fetched_at=None):
    """缓存交易日历"""
    if fetched_at is None:
        fetched_at = time.time()
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT OR REPLACE INTO trade_days_cache
               (year, days, fetched_at) VALUES (?, ?, ?)""",
            (year, json.dumps(days), fetched_at),
        )
        conn.commit()
    finally:
        conn.close()


def load_trade_days_cache(year):
    """加载缓存的交易日历"""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT days FROM trade_days_cache WHERE year=?", (year,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row['days'])
    finally:
        conn.close()


# ==================== Helpers ====================

def _row_to_backtest_dict(row):
    """将数据库行转换为完整的回测字典"""
    result = {
        'task_id': row['task_id'],
        'strategy': row['strategy'],
        'params': json.loads(row['params']) if row['params'] else {},
        'config': json.loads(row['config']) if row['config'] else {},
        'status': row['status'],
        'message': row['message'] or '',
        'summary': json.loads(row['summary']) if row['summary'] else {},
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
    }
    if row['result_data']:
        result['result_data'] = json.loads(row['result_data'])
    return result


def _row_to_backtest_summary(row):
    """将数据库行转换为回测摘要（不含完整 result_data）"""
    return {
        'task_id': row['task_id'],
        'strategy': row['strategy'],
        'params': json.loads(row['params']) if row['params'] else {},
        'config': json.loads(row['config']) if row['config'] else {},
        'status': row['status'],
        'message': row['message'] or '',
        'summary': json.loads(row['summary']) if row['summary'] else {},
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
    }


# 启动时自动初始化
init_db()
