create schema if not exists staging;
create schema if not exists mart;

create table if not exists staging.events (
    event_id        uuid primary key,
    user_id         int,
    event_name      text,
    event_ts        timestamptz,
    client_ts       text,
    clock_skew_flag boolean,
    platform        text,
    app_version     text,
    channel         text,
    country         text,
    loaded_at       timestamptz default now()
);

create index if not exists events_user_ts_idx on staging.events (user_id, event_ts);
