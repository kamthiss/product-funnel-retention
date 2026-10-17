"""Генератор синтетических логов продуктовых событий в data/raw/events.csv."""
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

P = {
    'seed': 42,
    'n_users': 20000,
    'start': '2026-03-02',
    'signup_weeks': 12,
    'end': '2026-06-28',  # включительно
    'platform': {'ios': 0.40, 'android': 0.45, 'web': 0.15},
    'channel': {'organic': 0.40, 'paid_social': 0.25, 'ads': 0.20, 'referral': 0.15},
    'country': {'RU': 0.60, 'KZ': 0.20, 'BY': 0.10, 'UZ': 0.10},
    'p_signup': 0.70,
    'p_onboarding': 0.60,
    'android_onboarding_drop': 0.12,
    'p_activation': 0.50,
    'activation_days': 7,
    # вероятность вернуться на k-й неделе: c * (e + (1 - e) * exp(-(k - 1) / tau)),
    # c = p_return * mult[channel], e ~ Beta - уровень плато пользователя
    'p_return_active': 0.50,
    'p_return_inactive': 0.20,
    'engagement_beta': (1.5, 3.5),
    'novelty_tau_weeks': 2,
    'retention_mult': {'organic': 1.0, 'paid_social': 1 / 1.5, 'ads': 0.9, 'referral': 1.3},
    'sessions_per_week': 1.0,  # 1 + Poisson
    'p_project_in_session': 0.5,
    'releases': {'2.1.0': '2026-01-12', '2.2.0': '2026-03-23', '2.3.0': '2026-04-27', '2.3.1': '2026-05-07', '2.4.0': '2026-05-25'},
    'upgrade_lag_days': 5,
    'local_tz_version': '2.3.0',
    'p_dup': 0.03,
    'p_skew': 0.01,
    'p_bad_name': 0.002,
    'bad_names': ['projct_created', 'APP_OPEN', 'signup_complete', 'undefined', 'null'],
    'out': 'data/raw/events.csv',
}

DAY, WEEK = 86400, 7 * 86400

rng = np.random.default_rng(P['seed'])
start = pd.Timestamp(P['start'])
horizon = (pd.Timestamp(P['end']) + pd.Timedelta(days=1) - start).total_seconds()
n = P['n_users']


def pick(d):
    return rng.choice(list(d), size=n, p=list(d.values()))


users = pd.DataFrame({
    'user_id': np.arange(1, n + 1),
    'platform': pick(P['platform']),
    'channel': pick(P['channel']),
    'country': pick(P['country']),
    't0': rng.uniform(0, P['signup_weeks'] * WEEK, n),
    'lag': rng.exponential(P['upgrade_lag_days'] * DAY, n),
    'eng': rng.beta(*P['engagement_beta'], n),
})

rows = []
for u in users.itertuples():
    t = u.t0
    rows.append((u.user_id, 'signup_started', t))
    if rng.random() >= P['p_signup']:
        continue
    t += 30 + rng.exponential(90)
    rows.append((u.user_id, 'signup_completed', t))

    active = False
    p_onb = P['p_onboarding'] - P['android_onboarding_drop'] * (u.platform == 'android')
    if rng.random() < p_onb:
        t += 60 + rng.exponential(180)
        rows.append((u.user_id, 'onboarding_completed', t))
        if rng.random() < P['p_activation']:
            # квадрат смещает первый проект к началу 7-дневного окна
            t += P['activation_days'] * DAY * rng.random() ** 2
            rows.append((u.user_id, 'app_open', t))
            rows.append((u.user_id, 'project_created', t + rng.exponential(300)))
            active = True

    c = P['p_return_active' if active else 'p_return_inactive'] * P['retention_mult'][u.channel]
    k = 1
    while t + k * WEEK < horizon:
        if rng.random() < c * (u.eng + (1 - u.eng) * np.exp(-(k - 1) / P['novelty_tau_weeks'])):
            n_sess = 1 + rng.poisson(P['sessions_per_week'])
            for s in rng.uniform(t + k * WEEK, t + (k + 1) * WEEK, n_sess):
                rows.append((u.user_id, 'app_open', s))
                if active and rng.random() < P['p_project_in_session']:
                    rows.append((u.user_id, 'project_created', s + rng.exponential(300)))
        k += 1

df = pd.DataFrame(rows, columns=['user_id', 'event_name', 't'])
df = df[df.t < horizon].merge(users, on='user_id')

# новый юзер ставит последнюю версию, старый обновляется с задержкой lag
rel = [(v, (pd.Timestamp(d) - start).total_seconds()) for v, d in P['releases'].items()]
df['app_version'] = rel[0][0]
for v, r in rel[1:]:
    df.loc[(df.t >= r) & ((df.t >= r + df.lag) | (df.t0 >= r)), 'app_version'] = v

m = len(df)
df['server_ts'] = start + pd.to_timedelta(df.t, unit='s')
client = df.server_ts - pd.to_timedelta(rng.exponential(1.5, m), unit='s')
df['event_id'] = [str(uuid.UUID(bytes=rng.bytes(16), version=4)) for _ in range(m)]

df['_bad'] = rng.random(m) < P['p_bad_name']
df.loc[df._bad, 'event_name'] = rng.choice(P['bad_names'], df._bad.sum())

df['_skew'] = rng.random(m) < P['p_skew']
years = rng.choice([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5], df._skew.sum())
client[df._skew] = [c.replace(year=c.year + y) for c, y in zip(client[df._skew], years)]

local = df.app_version == P['local_tz_version']
client[local] += pd.Timedelta(hours=3)
df['client_ts'] = client.dt.strftime('%Y-%m-%dT%H:%M:%S.%f').str[:-3] + np.where(local, '', 'Z')

df['_dup'] = False
dup = df[rng.random(m) < P['p_dup']].copy()
dup['server_ts'] += pd.to_timedelta(rng.integers(1, 121, len(dup)), unit='s')
dup['_dup'] = True
df = pd.concat([df, dup]).sort_values('server_ts', kind='stable')
df['server_ts'] = df.server_ts.dt.strftime('%Y-%m-%dT%H:%M:%S.%f').str[:-3] + 'Z'

out = Path(__file__).resolve().parents[1] / P['out']
out.parent.mkdir(parents=True, exist_ok=True)
cols = ['event_id', 'user_id', 'event_name', 'client_ts', 'server_ts',
        'platform', 'app_version', 'channel', 'country']
df[cols].to_csv(out, index=False)

print(f'rows: {len(df)}')
print(f'duplicates:      {df._dup.mean():.2%}')
print(f'skewed clock:    {df._skew.mean():.2%}')
print(f'local tz (2.3.0): {(df.app_version == P["local_tz_version"]).mean():.2%}')
print(f'bad event_name:  {df._bad.mean():.2%}')
