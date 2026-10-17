"""Загрузка data/clean/events.csv в staging.events (идемпотентно)."""
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / 'data/clean/events.csv'

env = dict(
    line.strip().split('=', 1)
    for line in (ROOT / '.env').read_text().splitlines()
    if '=' in line and not line.startswith('#')
)
conninfo = psycopg.conninfo.make_conninfo(
    host=env['POSTGRES_HOST'], port=env['POSTGRES_PORT'], dbname=env['POSTGRES_DB'],
    user=env['POSTGRES_USER'], password=env['POSTGRES_PASSWORD'],
)

with psycopg.connect(conninfo) as conn, conn.cursor() as cur, CSV.open() as f:
    cur.execute((ROOT / 'sql/01_schema.sql').read_text())

    # временная таблица повторяет заголовок CSV, всё text - типы приводятся при INSERT
    header = f.readline().strip().split(',')
    f.seek(0)
    cur.execute(f"create temp table tmp_events ({', '.join(c + ' text' for c in header)}) on commit drop")
    with cur.copy('copy tmp_events from stdin with (format csv, header true)') as cp:
        while data := f.read(1 << 20):
            cp.write(data)
    n_read = cur.execute('select count(*) from tmp_events').fetchone()[0]

    cur.execute("""
        insert into staging.events (event_id, user_id, event_name, event_ts, client_ts, clock_skew_flag,
                                    platform, app_version, channel, country)
        select event_id::uuid, user_id::int, event_name, event_ts::timestamptz, client_ts,
               clock_skew_flag::boolean, platform, app_version, channel, country
        from tmp_events
        on conflict (event_id) do nothing
    """)
    n_ins = cur.rowcount
    n_total = cur.execute('select count(*) from staging.events').fetchone()[0]

print(f'read:     {n_read}')
print(f'inserted: {n_ins}')
print(f'staging.events total: {n_total}')
