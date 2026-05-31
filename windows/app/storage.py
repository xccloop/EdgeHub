"""SQLite storage with aiosqlite + WAL + serialized write queue."""

import asyncio, json, time, os, csv, io
import aiosqlite

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "edgehub.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

_write_queue: asyncio.Queue = asyncio.Queue()
_db: aiosqlite.Connection | None = None
_retention_days = 7  # configurable

async def init_db():
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA synchronous=NORMAL")
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id TEXT    NOT NULL,
            ts       INTEGER NOT NULL,
            raw_json TEXT    NOT NULL
        )
    """)
    await _db.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_board_ts ON telemetry(board_id, ts)")
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS commands (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id TEXT    NOT NULL,
            ts       INTEGER NOT NULL,
            cmd      TEXT    NOT NULL,
            seq      INTEGER NOT NULL,
            response TEXT,
            status   TEXT    DEFAULT 'pending'
        )
    """)
    await _db.commit()
    asyncio.create_task(_writer_loop())
    asyncio.create_task(_cleanup_loop())

async def _writer_loop():
    while True:
        sql, params = await _write_queue.get()
        try:
            await _db.execute(sql, params)
            await _db.commit()
        except Exception as e:
            print(f"[storage] write error: {e}")

async def _cleanup_loop():
    while True:
        await asyncio.sleep(3600)  # hourly
        cutoff = int((time.time() - _retention_days * 86400) * 1000)
        await _write_queue.put(("DELETE FROM telemetry WHERE ts < ?", (cutoff,)))
        await _write_queue.put(("DELETE FROM commands WHERE ts < ?", (cutoff,)))

def set_retention(days: int):
    global _retention_days
    _retention_days = max(1, min(days, 365))

# ── Public API ────────────────────────────────────────

async def insert_telemetry(board_id: str, ts: int, raw: dict):
    await _write_queue.put((
        "INSERT INTO telemetry(board_id, ts, raw_json) VALUES(?,?,?)",
        (board_id, ts, json.dumps(raw, ensure_ascii=False)),
    ))

async def insert_command(board_id: str, ts: int, cmd: str, seq: int):
    await _write_queue.put((
        "INSERT INTO commands(board_id, ts, cmd, seq, status) VALUES(?,?,?,?,?)",
        (board_id, ts, cmd, seq, 'pending'),
    ))

async def update_command_response(seq: int, response: str, status: str):
    await _write_queue.put((
        "UPDATE commands SET response=?, status=? WHERE seq=?",
        (response, status, seq),
    ))

async def query_history(board_id: str, from_ts: int, to_ts: int, limit: int = 5000):
    limit = min(limit, 10000)
    # enforce 1-hour max window
    if to_ts - from_ts > 3600_000:
        to_ts = from_ts + 3600_000
        truncated = True
    else:
        truncated = False
    cursor = await _db.execute(
        "SELECT ts, raw_json FROM telemetry WHERE board_id=? AND ts>=? AND ts<=? ORDER BY ts ASC LIMIT ?",
        (board_id, from_ts, to_ts, limit),
    )
    rows = await cursor.fetchall()
    points = [{"ts": ts, "raw": json.loads(raw)} for ts, raw in rows]
    return {"points": points, "truncated": truncated, "count": len(points)}

async def export_csv(board_id: str, from_ts: int, to_ts: int):
    cursor = await _db.execute(
        "SELECT ts, raw_json FROM telemetry WHERE board_id=? AND ts>=? AND ts<=? ORDER BY ts ASC",
        (board_id, from_ts, to_ts),
    )
    rows = await cursor.fetchall()
    if not rows:
        return ""
    # collect all field keys for CSV columns
    all_keys: set[str] = set()
    parsed = []
    for ts, raw in rows:
        obj = json.loads(raw)
        flat = _flatten(obj)
        parsed.append((ts, flat))
        all_keys.update(flat.keys())
    columns = sorted(all_keys)
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["ts"] + columns)
    for ts, flat in parsed:
        w.writerow([ts] + [flat.get(k, "") for k in columns])
    return output.getvalue()

def _flatten(obj: dict, prefix: str = "") -> dict:
    result = {}
    for k, v in obj.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            result[prefix + k] = v
        elif isinstance(v, dict):
            result.update(_flatten(v, prefix + k + "."))
    return result
