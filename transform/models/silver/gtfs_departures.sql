-- Scheduled departures per stop and line, for the days we have live snapshots of.
-- The date= folder would shadow GTFS's own `date` column, hence hive_partitioning = false.
-- reads every weekly timetable then keeps the newest; prune old gtfs/ partitions if this gets slow
{% set gtfs = var("bronze") ~ "/gtfs/*/" %}
with
latest as (
    select max(regexp_extract(filename, 'date=([0-9-]+)', 1)) as d
    from read_csv('{{ gtfs }}routes.txt', filename = true, all_varchar = true, hive_partitioning = false)
),
gtfs_file as (
    select * from read_csv('{{ gtfs }}routes.txt', filename = true, all_varchar = true, hive_partitioning = false)
    where filename like '%date=' || (select d from latest) || '%'
),
trips as (
    select * from read_csv('{{ gtfs }}trips.txt', filename = true, all_varchar = true, hive_partitioning = false)
    where filename like '%date=' || (select d from latest) || '%'
),
stop_times as (
    select trip_id, stop_id, departure_time
    from read_csv('{{ gtfs }}stop_times.txt', filename = true, all_varchar = true, hive_partitioning = false)
    where filename like '%date=' || (select d from latest) || '%'
),
calendar as (
    select * from read_csv('{{ gtfs }}calendar.txt', filename = true, all_varchar = true, hive_partitioning = false)
    where filename like '%date=' || (select d from latest) || '%'
),
calendar_dates as (
    select service_id, strptime(date, '%Y%m%d')::date as d, exception_type
    from read_csv('{{ gtfs }}calendar_dates.txt', filename = true, all_varchar = true, hive_partitioning = false)
    where filename like '%date=' || (select d from latest) || '%'
),
-- Trips after midnight belong to the previous service day, so include the day before too.
days as (
    select distinct d from (
        select (fetched_at::timestamptz at time zone 'Europe/Brussels')::date as d from {{ ref('stib_waiting') }}
        union all
        select (fetched_at::timestamptz at time zone 'Europe/Brussels')::date - 1 from {{ ref('stib_waiting') }}
    )
),
active as (
    (
        select c.service_id, days.d
        from calendar c
        join days on days.d between strptime(c.start_date, '%Y%m%d')::date and strptime(c.end_date, '%Y%m%d')::date
        where [c.monday, c.tuesday, c.wednesday, c.thursday, c.friday, c.saturday, c.sunday][isodow(days.d)] = '1'
        union
        select service_id, d from calendar_dates where exception_type = '1' and d in (select d from days)
    )
    except
    select service_id, d from calendar_dates where exception_type = '2'
)
select
    st.stop_id,
    r.route_short_name as line_id,
    -- GTFS route_type: 0 tram, 1 metro, 3 bus
    case r.route_type when '0' then 'tram' when '1' then 'metro' when '3' then 'bus' else 'other' end as mode,
    -- GTFS times can pass 24:00; count seconds from local midnight of the service day.
    timezone('Europe/Brussels', a.d::timestamp + to_seconds(
        split_part(st.departure_time, ':', 1)::int * 3600
        + split_part(st.departure_time, ':', 2)::int * 60
        + split_part(st.departure_time, ':', 3)::int)) as scheduled_departure
from stop_times st
join trips t using (trip_id)
join gtfs_file r on r.route_id = t.route_id
join active a on a.service_id = t.service_id
