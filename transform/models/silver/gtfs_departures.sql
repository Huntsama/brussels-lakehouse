-- Scheduled departures per stop and line, for the days we have live snapshots of.
-- Each live day uses the newest weekly timetable fetched on or before that day (the earliest one for days
-- before the first fetch): a new GTFS file only covers dates from its own start, so keeping only the newest
-- file would drop every earlier day from excess wait.
-- The date= folder would shadow GTFS's own `date` column, hence hive_partitioning = false.
{% set g = var("bronze") ~ "/gtfs/*/" %}
{% set opts = "filename = true, all_varchar = true, hive_partitioning = false" %}
{% set file_d = "regexp_extract(filename, 'date=([0-9-]+)', 1)::date as file_d" %}
with
routes as (select *, {{ file_d }} from read_csv('{{ g }}routes.txt', {{ opts }})),
trips as (select *, {{ file_d }} from read_csv('{{ g }}trips.txt', {{ opts }})),
stop_times as (select trip_id, stop_id, departure_time, {{ file_d }} from read_csv('{{ g }}stop_times.txt', {{ opts }})),
calendar as (select *, {{ file_d }} from read_csv('{{ g }}calendar.txt', {{ opts }})),
calendar_dates as (
    select service_id, strptime(date, '%Y%m%d')::date as d, exception_type, {{ file_d }}
    from read_csv('{{ g }}calendar_dates.txt', {{ opts }})
),
-- Trips after midnight belong to the previous service day, so include the day before too.
days as (
    select distinct d from (
        select (fetched_at::timestamptz at time zone 'Europe/Brussels')::date as d from {{ ref('stib_waiting') }}
        union all
        select (fetched_at::timestamptz at time zone 'Europe/Brussels')::date - 1 from {{ ref('stib_waiting') }}
    )
),
files as (select distinct file_d from routes),
day_file as (
    select days.d,
           coalesce(max(files.file_d) filter (where files.file_d <= days.d), min(files.file_d)) as file_d
    from days cross join files
    group by days.d
),
active as (
    (
        select c.service_id, df.d, df.file_d
        from calendar c
        join day_file df on df.file_d = c.file_d
            and df.d between strptime(c.start_date, '%Y%m%d')::date and strptime(c.end_date, '%Y%m%d')::date
        where [c.monday, c.tuesday, c.wednesday, c.thursday, c.friday, c.saturday, c.sunday][isodow(df.d)] = '1'
        union
        select cd.service_id, cd.d, cd.file_d
        from calendar_dates cd
        join day_file df on df.file_d = cd.file_d and df.d = cd.d
        where cd.exception_type = '1'
    )
    except
    select service_id, d, file_d from calendar_dates where exception_type = '2'
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
join trips t on t.trip_id = st.trip_id and t.file_d = st.file_d
join routes r on r.route_id = t.route_id and r.file_d = t.file_d
join active a on a.service_id = t.service_id and a.file_d = t.file_d
