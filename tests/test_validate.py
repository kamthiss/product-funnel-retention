import pandas as pd
import pandera.pandas as pa
import pytest

import validate

BASE = dict(event_id='e1', user_id='1', event_name='app_open',
            client_ts='2026-03-02T10:00:00.000Z', server_ts='2026-03-02T10:00:00.000Z',
            platform='ios', app_version='2.1.0', channel='organic', country='RU')


def frame(*rows):
    return pd.DataFrame([BASE | r for r in rows], dtype=str)


def test_resent_event_id_keeps_earliest():
    raw = frame(dict(server_ts='2026-03-02T10:00:05.000Z'),
                dict(server_ts='2026-03-02T10:00:01.000Z'))
    df, _, n_dups, n_resent, _ = validate.validate(raw)
    assert len(df) == 1
    assert df.server_ts.item() == '2026-03-02T10:00:01.000Z'
    assert (n_dups, n_resent) == (1, 1)


def test_distinct_event_ids_same_second_kept():
    raw = frame(dict(event_id='e1'), dict(event_id='e2'))
    df, _, n_dups, _, _ = validate.validate(raw)
    assert sorted(df.event_id) == ['e1', 'e2']
    assert n_dups == 0


def test_bad_event_name_quarantined():
    raw = frame(dict(event_id='e1'), dict(event_id='e2', event_name='APP_OPEN'))
    df, q, _, _, _ = validate.validate(raw)
    assert list(df.event_id) == ['e1']
    assert q.set_index('event_id').reason.to_dict() == {'e2': 'bad_event_name'}


def test_empty_event_id_quarantined_as_schema():
    raw = frame(dict(event_id='e1'), dict(event_id=''))
    df, q, _, _, _ = validate.validate(raw)
    assert list(df.event_id) == ['e1']
    assert len(q) == 1
    assert q.event_id.item() == ''
    assert q.reason.item().startswith('schema')


def test_missing_column_raises():
    raw = frame(dict(event_id='e1')).drop(columns='country')
    with pytest.raises(pa.errors.SchemaError):
        validate.validate(raw)


def test_clock_skew_over_24h_flagged():
    raw = frame(dict(event_id='e1', client_ts='2026-03-03T10:00:00.001Z'),
                dict(event_id='e2', client_ts='2026-03-03T09:59:59.999Z'))
    df, _, _, _, _ = validate.validate(raw)
    assert df.set_index('event_id').clock_skew_flag.to_dict() == {'e1': True, 'e2': False}


def test_user_with_different_platforms_inconsistent():
    raw = frame(dict(event_id='e1', user_id='1', platform='ios'),
                dict(event_id='e2', user_id='1', platform='android'),
                dict(event_id='e3', user_id='2'), dict(event_id='e4', user_id='2'))
    _, _, _, _, inconsistent = validate.validate(raw)
    assert list(inconsistent.index) == [1]
    assert inconsistent.loc[1, 'platform'] == 2


def test_quarantine_over_threshold_exits_1(tmp_path):
    raw = frame(*[dict(event_id=f'e{i}') for i in range(9)], dict(event_id='bad', event_name='null'))
    assert 1 / len(raw) > validate.MAX_QUARANTINE_SHARE
    (tmp_path / 'data/raw').mkdir(parents=True)
    raw.to_csv(tmp_path / 'data/raw/events.csv', index=False)
    with pytest.raises(SystemExit) as e:
        validate.main(tmp_path)
    assert e.value.code == 1
