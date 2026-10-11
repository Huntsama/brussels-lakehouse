-- One row per (snapshot, stop, line, upcoming arrival).
with raw as (
    select fetched_at, unnest(data.results) as r
    from read_json_auto('{{ var("bronze") }}/stib_waiting/*/*.json*')
),
arrivals as (
    select
        fetched_at,
        r.pointid as stop_id,
        r.lineid as line_id,
        unnest(from_json(r.passingtimes, '[{"expectedArrivalTime": "VARCHAR"}]')).expectedArrivalTime as eta
    from raw
)
select
    fetched_at,
    stop_id,
    line_id,
    eta::timestamptz as expected_arrival,
    date_diff('second', fetched_at::timestamptz, eta::timestamptz) / 60.0 as minutes_until
from arrivals
where eta is not null
