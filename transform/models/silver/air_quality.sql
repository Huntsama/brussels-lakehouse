-- Hourly pollutant values per Brussels station; snapshots overlap, keep one row per hour.
with raw as (
    select fetched_at, unnest(data) as s
    from read_json_auto('{{ var("bronze") }}/ircel/*/*.json*')
),
v as (
    select fetched_at, s.station, s.pollutant, s.lat, s.lon, unnest(s."values") as x
    from raw
)
select
    station,
    pollutant,
    lat,
    lon,
    to_timestamp(x."timestamp" / 1000) as measured_at,
    x."value" as value_ugm3
from v
where x."value" is not null
qualify row_number() over (partition by station, pollutant, x."timestamp" order by fetched_at desc) = 1
