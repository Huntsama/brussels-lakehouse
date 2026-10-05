-- Belgian grid load (MW), 15-minute resolution; latest revision wins.
with raw as (
    select fetched_at, unnest(data.results) as r
    from read_json_auto('{{ var("bronze") }}/elia/*/*.json')
)
select r.datetime::timestamptz as measured_at, r.totalload as load_mw
from raw
qualify row_number() over (partition by r.datetime order by fetched_at desc) = 1
