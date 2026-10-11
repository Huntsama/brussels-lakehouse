-- One row per line from the newest timetable: STIB's own line colours, for the dashboard badges.
{% set gtfs = var("bronze") ~ "/gtfs/*/" %}
with routes as (
    select *, regexp_extract(filename, 'date=([0-9-]+)', 1) as d
    from read_csv('{{ gtfs }}routes.txt', filename = true, all_varchar = true, hive_partitioning = false)
)
select route_short_name as line_id,
       '#' || route_color as color,
       '#' || coalesce(nullif(route_text_color, ''), 'FFFFFF') as text_color
from routes
where d = (select max(d) from routes)
qualify row_number() over (partition by route_short_name order by route_id) = 1
