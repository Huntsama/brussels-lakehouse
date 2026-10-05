-- Latest known name and position per stop.
with raw as (
    select fetched_at, unnest(data.results) as r
    from read_json_auto('{{ var("bronze") }}/stib_stops/*/*.json')
)
select
    r.id as stop_id,
    from_json(r.name, '{"fr": "VARCHAR", "nl": "VARCHAR"}') ->> 'fr' as name_fr,
    from_json(r.name, '{"fr": "VARCHAR", "nl": "VARCHAR"}') ->> 'nl' as name_nl,
    (r.gpscoordinates::json ->> 'latitude')::double as lat,
    (r.gpscoordinates::json ->> 'longitude')::double as lon
from raw
qualify row_number() over (partition by r.id order by fetched_at desc) = 1
