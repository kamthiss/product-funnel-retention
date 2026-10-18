import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.db


@pytest.fixture(scope='module')
def cur():
    env = dict(line.strip().split('=', 1)
               for line in (ROOT / '.env').read_text().splitlines()
               if '=' in line and not line.startswith('#'))
    with psycopg.connect(host=env['POSTGRES_HOST'], port=env['POSTGRES_PORT'], dbname=env['POSTGRES_DB'],
                         user=env['POSTGRES_USER'], password=env['POSTGRES_PASSWORD'],
                         autocommit=True) as conn:
        yield conn.cursor()


def scalar(cur, sql):
    return cur.execute(sql).fetchone()[0]


def test_funnel_never_grows(cur):
    assert scalar(cur, 'select count(*) from mart.funnel') > 0
    assert scalar(cur, """
        select count(*) from (
            select users, lag(users) over (partition by dim, segment order by step_no) as prev
            from mart.funnel
        ) t
        where users > prev
    """) == 0


def test_users_match_staging(cur):
    assert scalar(cur, 'select count(*) from mart.users') == \
        scalar(cur, 'select count(distinct user_id) from staging.events')


def test_reload_is_idempotent(cur):
    before = scalar(cur, 'select count(*) from staging.events')
    subprocess.run([sys.executable, ROOT / 'src/load.py'], check=True, capture_output=True)
    assert scalar(cur, 'select count(*) from staging.events') == before


def test_retention_only_fully_observed_weeks(cur):
    assert scalar(cur, 'select count(*) from mart.retention_weekly') > 0
    # регистрация в последний день недели может быть до 23:59, наблюдение кончается 2026-06-29 00:00
    assert scalar(cur, """
        select count(*) from mart.retention_weekly
        where (cohort_week + 6) + 7 * (week_n + 1) >= date '2026-06-29'
    """) == 0


def test_events_vs_users_conversion(cur):
    cur.execute((ROOT / 'sql/checks/events_vs_users.sql').read_text())
    row = dict(zip([c.name for c in cur.description], cur.fetchone()))
    assert float(row['conv_by_events']) == pytest.approx(0.87, abs=0.01)
    assert float(row['conv_by_users']) == pytest.approx(0.27, abs=0.01)
