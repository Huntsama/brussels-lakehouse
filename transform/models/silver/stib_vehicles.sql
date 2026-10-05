-- One row per vehicle seen in a snapshot.
with raw as (
    select fetched_at, unnest(data.results) as r
    from read_json_auto('{{ var("bronze") }}/stib_vehicles/*/*.json')
),
v as (
    select
        fetched_at,
        r.lineid as line_id,
        unnest(from_json(r.vehiclepositions,
            '[{"directionId": "VARCHAR", "pointId": "VARCHAR", "distanceFromPoint": "INTEGER"}]')) as p
    from raw
)
select fetched_at, line_id, p.directionId as direction_id, p.pointId as stop_id, p.distanceFromPoint as metres_from_stop
from v
