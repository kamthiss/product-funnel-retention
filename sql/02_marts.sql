drop table if exists mart.users;
create table mart.users as
with s as (
    select
        user_id,
        min(event_ts) filter (where event_name = 'signup_started')       as signup_started_ts,
        min(event_ts) filter (where event_name = 'signup_completed')     as signup_completed_ts,
        min(event_ts) filter (where event_name = 'onboarding_completed') as onboarding_ts
    from staging.events
    group by user_id
),
attrs as (
    select distinct on (user_id) user_id, platform, channel, country
    from staging.events
    order by user_id, event_ts
)
select
    s.user_id,
    a.platform,
    a.channel,
    a.country,
    s.signup_started_ts,
    s.signup_completed_ts,
    s.onboarding_ts,
    (
        select min(e.event_ts)
        from staging.events e
        where e.user_id = s.user_id
          and e.event_name = 'project_created'
          and e.event_ts >= s.signup_completed_ts
          and e.event_ts < s.signup_completed_ts + interval '7 days'
    ) as activation_ts,
    date_trunc('week', s.signup_completed_ts at time zone 'UTC')::date as cohort_week
from s
join attrs a using (user_id);

alter table mart.users add primary key (user_id);

drop table if exists mart.events;
create table mart.events as
select
    event_id, user_id, event_name, event_ts, client_ts, clock_skew_flag,
    platform, app_version, channel, country,
    event_name = 'project_created' as is_key_action
from staging.events;

alter table mart.events add primary key (event_id);
create index on mart.events (user_id, event_ts);
