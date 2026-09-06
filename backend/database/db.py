import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from backend.config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS investigations (
 id TEXT PRIMARY KEY, claim TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL,
 stage TEXT NOT NULL, result_json TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS search_queries (id INTEGER PRIMARY KEY, investigation_id TEXT, query TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS sources (id INTEGER PRIMARY KEY, investigation_id TEXT, url TEXT, title TEXT, domain TEXT, source_type TEXT, snippet TEXT, published_at TEXT, independence_group TEXT);
CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, investigation_id TEXT, url TEXT, content_hash TEXT, text TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS evidence (id INTEGER PRIMARY KEY, investigation_id TEXT, url TEXT, stance TEXT, strength REAL, excerpt TEXT, reasoning TEXT);
CREATE TABLE IF NOT EXISTS entities (id INTEGER PRIMARY KEY, investigation_id TEXT, name TEXT, entity_type TEXT);
CREATE TABLE IF NOT EXISTS relationships (id INTEGER PRIMARY KEY, investigation_id TEXT, source TEXT, target TEXT, relation TEXT);
CREATE TABLE IF NOT EXISTS timeline_events (id INTEGER PRIMARY KEY, investigation_id TEXT, event_date TEXT, title TEXT, url TEXT);
CREATE TABLE IF NOT EXISTS contradictions (id INTEGER PRIMARY KEY, investigation_id TEXT, explanation TEXT, severity TEXT);
CREATE TABLE IF NOT EXISTS claims (id INTEGER PRIMARY KEY, investigation_id TEXT, subject TEXT, action TEXT, object TEXT, location TEXT, claim_type TEXT);
CREATE TABLE IF NOT EXISTS investigation_runs (id INTEGER PRIMARY KEY, investigation_id TEXT, stage TEXT, message TEXT, created_at TEXT);
"""


def now(): return datetime.now(timezone.utc).isoformat()


def initialize():
    os.makedirs(os.path.dirname(settings.database_path) or ".", exist_ok=True)
    with connect() as con: con.executescript(SCHEMA)


@contextmanager
def connect():
    con = sqlite3.connect(settings.database_path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally: con.close()


def create_investigation(case_id, claim, mode):
    stamp = now()
    with connect() as con:
        con.execute("INSERT INTO investigations VALUES (?, ?, ?, 'queued', 'Case initialization', NULL, NULL, ?, ?)", (case_id, claim, mode, stamp, stamp))


def update_status(case_id, status, stage, error=None):
    with connect() as con:
        con.execute("UPDATE investigations SET status=?,stage=?,error=?,updated_at=? WHERE id=?", (status, stage, error, now(), case_id))
        con.execute("INSERT INTO investigation_runs(investigation_id,stage,message,created_at) VALUES (?, ?, ?, ?)", (case_id, stage, status, now()))


def save_result(case_id, result):
    with connect() as con:
        con.execute("UPDATE investigations SET status='complete', stage='Case board ready', result_json=?, updated_at=? WHERE id=?", (json.dumps(result), now(), case_id))


def get_case(case_id):
    with connect() as con:
        row = con.execute("SELECT * FROM investigations WHERE id=?", (case_id,)).fetchone()
    if not row: return None
    item = dict(row)
    if item.get("result_json"): item["result"] = json.loads(item["result_json"])
    return item


def record(case_id, table, rows):
    if not rows: return
    allowed = {"search_queries": ("investigation_id,query,created_at", 3), "sources": ("investigation_id,url,title,domain,source_type,snippet,published_at,independence_group", 8), "evidence": ("investigation_id,url,stance,strength,excerpt,reasoning", 6)}
    if table not in allowed: return
    cols, count = allowed[table]
    marks = ",".join("?" * count)
    with connect() as con:
        con.executemany(f"INSERT INTO {table} ({cols}) VALUES ({marks})", rows)
