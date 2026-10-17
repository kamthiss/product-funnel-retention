-- signup_completed -> activation: наивно по событиям против уникальных пользователей.
-- По событиям в числителе все project_created, включая повторные после окна активации.
-- По пользователям - определение из mart.users: project_created в [signup_completed_ts, +7 дней).
with ev as (
    select
        count(*) filter (where event_name = 'signup_completed') as completed_events,
        count(*) filter (where event_name = 'project_created')  as project_events
    from mart.events
),
us as (
    select
        count(distinct user_id) filter (where signup_completed_ts is not null) as completed_users,
        count(distinct user_id) filter (where activation_ts is not null)       as activated_users
    from mart.users
)
select
    completed_events,
    project_events,
    round(project_events::numeric / completed_events, 4) as conv_by_events,
    completed_users,
    activated_users,
    round(activated_users::numeric / completed_users, 4) as conv_by_users
from ev, us;
