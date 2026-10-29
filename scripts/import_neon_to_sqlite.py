"""Import user data from neon.dump (Postgres plain-SQL export) into local SQLite.

Extracts the COPY blocks for backtest_runs (19 rows) and strategies (3 rows)
from the pg_restore plain dump and inserts them via the app's SQLAlchemy models.
"""

import asyncio
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import AsyncSessionLocal, init_db  # noqa: E402
from app.models.backtest_run import BacktestRun  # noqa: E402
from app.models.strategy import Strategy  # noqa: E402

DUMP_SQL = Path("/tmp/neon_dump.sql")


def pg_unescape(field: str) -> str | None:
    """Reverse PostgreSQL COPY text-format escaping."""
    if field == r"\N":
        return None
    out = []
    i = 0
    while i < len(field):
        c = field[i]
        if c == "\\" and i + 1 < len(field):
            n = field[i + 1]
            if n == "n":
                out.append("\n")
            elif n == "t":
                out.append("\t")
            elif n == "r":
                out.append("\r")
            elif n == "b":
                out.append("\b")
            elif n == "f":
                out.append("\f")
            elif n == "v":
                out.append("\v")
            elif n == "\\":
                out.append("\\")
            else:
                out.append(n)
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def extract_copy_block(table: str) -> list[list[str | None]]:
    """Extract all rows of a COPY block as lists of unescaped fields."""
    content = DUMP_SQL.read_text(encoding="utf-8", errors="replace")
    m = re.search(
        rf"^COPY public\.{table} \([^)]+\) FROM stdin;\n(.*?)^\\\.$",
        content,
        re.DOTALL | re.MULTILINE,
    )
    if not m:
        return []
    rows = []
    for line in m.group(1).split("\n"):
        if not line.strip():
            continue
        fields = line.split("\t")
        rows.append([pg_unescape(f) for f in fields])
    return rows


def parse_dt(val: str | None) -> dt.datetime | None:
    if not val:
        return None
    val = val.replace("+00", "+00:00")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S%z"):
        try:
            return dt.datetime.strptime(val, fmt)
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(val)
    except ValueError:
        return None


def parse_json(val: str | None):
    import json

    if not val:
        return None
    try:
        return json.loads(val)
    except Exception:
        return None


async def main():
    await init_db()

    # --- backtest_runs -----------------------------------------------------
    bt_rows = extract_copy_block("backtest_runs")
    # columns: id, name, summary, chart_data, full_config, created_at,
    #          total_pnl_percent, win_rate, total_trades, timeframe, symbol
    count_bt = 0
    async with AsyncSessionLocal() as session:
        for r in bt_rows:
            if len(r) < 11:
                continue
            exists = await session.get(BacktestRun, r[0])
            if exists:
                continue
            session.add(
                BacktestRun(
                    id=r[0],
                    name=r[1] or "(unnamed)",
                    summary=parse_json(r[2]),
                    chart_data=parse_json(r[3]),
                    full_config=parse_json(r[4]),
                    created_at=parse_dt(r[5]),
                    total_pnl_percent=float(r[6]) if r[6] else None,
                    win_rate=float(r[7]) if r[7] else None,
                    total_trades=int(r[8]) if r[8] else None,
                    timeframe=r[9],
                    symbol=r[10],
                )
            )
            count_bt += 1
        await session.commit()
    print(f"backtest_runs imported: {count_bt} (of {len(bt_rows)} in dump)")

    # --- strategies ----------------------------------------------------------
    st_rows = extract_copy_block("strategies")
    # columns: id, name, version, description, author, base_timeframe,
    #          position_side, config, is_active, created_at, updated_at,
    #          total_runs, success_rate, last_run_at
    count_st = 0
    async with AsyncSessionLocal() as session:
        for r in st_rows:
            if len(r) < 14:
                continue
            exists = await session.get(Strategy, int(r[0]))
            if exists:
                continue
            session.add(
                Strategy(
                    id=int(r[0]),
                    name=r[1],
                    version=r[2] or "1.0.0",
                    description=r[3],
                    author=r[4],
                    base_timeframe=r[5] or "1h",
                    position_side=r[6] or "both",
                    config=r[7] or "{}",
                    is_active=(r[8] or "t").startswith(("t", "1")),
                    created_at=parse_dt(r[9]),
                    updated_at=parse_dt(r[10]),
                    total_runs=int(r[11]) if r[11] else 0,
                    success_rate=float(r[12]) if r[12] else 0.0,
                    last_run_at=parse_dt(r[13]),
                )
            )
            count_st += 1
        await session.commit()
    print(f"strategies imported: {count_st} (of {len(st_rows)} in dump)")


if __name__ == "__main__":
    asyncio.run(main())
