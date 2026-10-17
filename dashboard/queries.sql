-- Воронка регистрации
select
    step_no,
    case step
        when 'signup_started'       then 'Начали регистрацию'
        when 'signup_completed'     then 'Завершили регистрацию'
        when 'onboarding_completed' then 'Прошли онбординг'
        when 'activation'           then 'Активировались'
    end as step,
    users,
    conv_first
from mart.funnel
where dim = 'total'
order by step_no;


-- Конверсия по платформам
select
    step_no,
    case step
        when 'signup_started'       then '1. Начали регистрацию'
        when 'signup_completed'     then '2. Завершили регистрацию'
        when 'onboarding_completed' then '3. Прошли онбординг'
        when 'activation'           then '4. Активировались'
    end as step,
    segment as platform,
    users,
    conv_first
from mart.funnel
where dim = 'platform'
order by step_no, platform;


-- Retention когорт по неделям
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


-- Retention по каналам
-- неделя 0 по сути активация, поэтому с 1-й; взвешено по когортам,
-- на поздних неделях участвуют только когорты, которые до них дожили
select
    week_n,
    segment as channel,
    round(sum(retained)::numeric / sum(cohort_size), 4) as retention
from mart.retention_by_segment
where dim = 'channel' and week_n between 1 and 8
group by week_n, segment
order by week_n, channel;


-- Начали регистрацию
select users as "Начали регистрацию"
from mart.funnel
where dim = 'total' and step_no = 1;


-- Активировались
select users as "Активировались"
from mart.funnel
where dim = 'total' and step_no = 4;


-- Конверсия в активацию
select conv_first as "Конверсия в активацию"
from mart.funnel
where dim = 'total' and step_no = 4;


-- Retention недели 4
select round(sum(retained)::numeric / sum(cohort_size), 4) as "Retention недели 4"
from mart.retention_weekly
where week_n = 4;
