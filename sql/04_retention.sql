create or replace function mart.obs_end() returns timestamptz
language sql immutable as $$ select timestamptz '2026-06-29 00:00:00+00' $$;

drop view if exists mart.retention_weekly;
drop view if exists mart.retention_by_segment;

create view mart.retention_by_segment as
with u as (
    select user_id, channel, platform, cohort_week, signup_completed_ts
    from mart.users
    where signup_completed_ts is not null
),
act as (
    select distinct
        e.user_id,
        floor(extract(epoch from e.event_ts - u.signup_completed_ts) / (7 * 86400))::int as week_n
    from mart.events e
    join u using (user_id)
    where e.is_key_action
      and e.event_ts >= u.signup_completed_ts
),
cells as (
    -- cohort_week + 7d + 7(N+1)d <= obs_end  <=>  N <= floor(D / 7d) - 2, D = obs_end - cohort_week
    select u.*, w.week_n
    from u
    cross join lateral generate_series(
        0,
        floor(extract(epoch from mart.obs_end() - (u.cohort_week::timestamp at time zone 'UTC')) / (7 * 86400))::int - 2
    ) as w(week_n)
)
select
    case
        when grouping(c.channel) = 0  then 'channel'
        when grouping(c.platform) = 0 then 'platform'
        else 'total'
    end as dim,
    coalesce(c.channel, c.platform, 'all') as segment,
    c.cohort_week,
    c.week_n,
    count(distinct c.user_id) as cohort_size,
    count(distinct a.user_id) as retained,
    round(count(distinct a.user_id)::numeric / count(distinct c.user_id), 4) as retention
from cells c
left join act a on a.user_id = c.user_id and a.week_n = c.week_n
group by grouping sets (
    (c.cohort_week, c.week_n),
    (c.channel, c.cohort_week, c.week_n),
    (c.platform, c.cohort_week, c.week_n)
)
having count(distinct c.user_id) >= 100;

create view mart.retention_weekly as
select cohort_week, week_n, cohort_size, retained, retention
from mart.retention_by_segment
where dim = 'total';
