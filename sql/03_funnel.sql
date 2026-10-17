create or replace view mart.funnel as
with u as (
    -- depth = число шагов, пройденных подряд с первого: строгая воронка
    select
        user_id, platform, channel,
        case
            when signup_started_ts is null   then 0
            when signup_completed_ts is null then 1
            when onboarding_ts is null       then 2
            when activation_ts is null       then 3
            else 4
        end as depth
    from mart.users
),
steps (step_no, step) as (
    values (1, 'signup_started'), (2, 'signup_completed'), (3, 'onboarding_completed'), (4, 'activation')
),
agg as (
    select
        case
            when grouping(u.platform) = 0 then 'platform'
            when grouping(u.channel) = 0  then 'channel'
            else 'total'
        end as dim,
        coalesce(u.platform, u.channel, 'all') as segment,
        s.step_no,
        s.step,
        count(distinct u.user_id) as users
    from u
    join steps s on u.depth >= s.step_no
    group by grouping sets (
        (s.step_no, s.step),
        (u.platform, s.step_no, s.step),
        (u.channel, s.step_no, s.step)
    )
)
select
    dim, segment, step_no, step, users,
    round(users::numeric / lag(users) over w, 4)         as conv_prev,
    round(users::numeric / first_value(users) over w, 4) as conv_first
from agg
window w as (partition by dim, segment order by step_no);
