-- Воронка: всего
select step_no, step, users, conv_first
from mart.funnel
where dim = 'total'
order by step_no;


-- Воронка по platform
select step_no, step, segment as platform, users, conv_first
from mart.funnel
where dim = 'platform'
order by step_no, platform;


-- Retention: когорта x неделя 0-8
select
    cohort_week,
    max(cohort_size) as cohort_size,
    max(retention) filter (where week_n = 0) as w0,
    max(retention) filter (where week_n = 1) as w1,
    max(retention) filter (where week_n = 2) as w2,
    max(retention) filter (where week_n = 3) as w3,
    max(retention) filter (where week_n = 4) as w4,
    max(retention) filter (where week_n = 5) as w5,
    max(retention) filter (where week_n = 6) as w6,
    max(retention) filter (where week_n = 7) as w7,
    max(retention) filter (where week_n = 8) as w8
from mart.retention_weekly
where week_n <= 8
group by cohort_week
order by cohort_week;


-- Retention по channel, недели 0-8
-- взвешено по когортам; на поздних неделях участвуют только когорты, которые до них дожили
select
    week_n,
    segment as channel,
    round(sum(retained)::numeric / sum(cohort_size), 4) as retention
from mart.retention_by_segment
where dim = 'channel' and week_n <= 8
group by week_n, segment
order by week_n, channel;


-- KPI
select
    max(users) filter (where step_no = 1)      as total_users,
    max(users) filter (where step_no = 4)      as activated,
    max(conv_first) filter (where step_no = 4) as activation_rate,
    (
        select round(sum(retained)::numeric / sum(cohort_size), 4)
        from mart.retention_weekly
        where week_n = 4
    ) as retention_w4
from mart.funnel
where dim = 'total';
