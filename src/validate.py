"""Валидация data/raw/events.csv: data/clean/events.csv и data/quarantine/events.csv."""
from pathlib import Path

import pandas as pd
import pandera.pandas as pa

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ['signup_started', 'signup_completed', 'onboarding_completed', 'project_created', 'app_open']
TS_FMT = '%Y-%m-%dT%H:%M:%S.%fZ'

schema = pa.DataFrameSchema({
    'event_id': pa.Column(str, pa.Check.str_length(min_value=1)),
    'user_id': pa.Column(int, coerce=True),
    'event_name': pa.Column(str),
    'client_ts': pa.Column(str),
    'server_ts': pa.Column(str, pa.Check(
        lambda s: pd.to_datetime(s, format=TS_FMT, utc=True, errors='coerce').notna(), name='utc_iso')),
    'platform': pa.Column(str),
    'app_version': pa.Column(str),
    'channel': pa.Column(str),
    'country': pa.Column(str),
})

# keep_default_na=False: иначе event_name 'null' и пустые строки станут NaN и уйдут в схему
raw = pd.read_csv(ROOT / 'data/raw/events.csv', dtype=str, keep_default_na=False)

try:
    df = schema.validate(raw, lazy=True)
    q_schema = raw.iloc[:0].assign(reason='')
except pa.errors.SchemaErrors as e:
    # ошибки без индекса - уровня колонки; если их не вызвали плохие строки
    # (например, колонки нет), повторная валидация ниже упадёт сама
    fc = e.failure_cases.dropna(subset=['index'])
    reason = fc.groupby(fc['index'].astype(int))['column'].first()
    q_schema = raw.loc[reason.index].assign(reason='schema:' + reason)
    df = schema.validate(raw.drop(reason.index))

df['ts'] = pd.to_datetime(df.server_ts, format=TS_FMT, utc=True)
n_valid = len(df)
resent = df.event_id.duplicated(keep=False)
n_resent_ids = df[resent].event_id.nunique()
df = df.sort_values('ts', kind='stable').drop_duplicates('event_id')
n_dups = n_valid - len(df)

bad = ~df.event_name.isin(EVENTS)
q_name = df[bad].assign(reason='bad_event_name')
df = df[~bad].copy()

client = pd.to_datetime(df.client_ts.str.removesuffix('Z'), format='ISO8601', errors='coerce')
df['skew'] = client - df.ts.dt.tz_localize(None)
df['clock_skew_flag'] = df['skew'].abs() > pd.Timedelta(hours=24)
df['event_ts'] = df.ts.dt.strftime('%Y-%m-%dT%H:%M:%S.%f').str[:-3] + 'Z'

nun = df.groupby('user_id')[['platform', 'channel', 'country']].nunique()
inconsistent = nun[(nun > 1).any(axis=1)]

cols = list(raw.columns)
quarantine = pd.concat([q_schema, q_name[cols + ['reason']]])
for path, out in [('data/clean/events.csv', df[cols + ['event_ts', 'clock_skew_flag']]),
                  ('data/quarantine/events.csv', quarantine)]:
    (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(ROOT / path, index=False)

skew_h = (df.groupby('app_version')['skew'].median().dt.total_seconds() / 3600).round(2)

print(f'raw rows:           {len(raw)}')
print(f'duplicates removed: {n_dups} (event_id resent: {n_resent_ids})')
print(f'quarantine:         {len(quarantine)}')
for r, c in quarantine.reason.value_counts().items():
    print(f'  {r}: {c}')
print(f'clean rows:         {len(df)}')
print(f'clock_skew_flag:    {df.clock_skew_flag.sum()} ({df.clock_skew_flag.mean():.2%})')
print(f'inconsistent users: {len(inconsistent)}')
if len(inconsistent):
    print(inconsistent.head(10).to_string())
print('median skew by app_version, hours:')
print(skew_h.to_string())
