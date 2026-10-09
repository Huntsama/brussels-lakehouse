-- One row per hour for Brussels: transit service, air and grid load side by side.
with transit as (
    select date_trunc('hour', fetched_at::timestamptz) as hour,
           median(minutes_until) filter (where minutes_until between 0 and 60) as median_wait_min,
           count(distinct stop_id) as stops_served
    from {{ ref('stib_waiting') }}
    group by 1
),
fleet as (
    select date_trunc('hour', fetched_at::timestamptz) as hour,
           count(*) / count(distinct fetched_at) as vehicles_avg
    from {{ ref('stib_vehicles') }}
    group by 1
),
air as (
    select date_trunc('hour', measured_at) as hour,
           avg(value_ugm3) filter (where pollutant = 'no2') as no2,
           avg(value_ugm3) filter (where pollutant = 'pm10') as pm10,
           avg(value_ugm3) filter (where pollutant = 'pm25') as pm25
    from {{ ref('air_quality') }}
    group by 1
),
punctuality as (
    select hour, median(excess_wait_min) as excess_wait_min
    from {{ ref('stop_line_hourly') }}
    group by 1
),
grid as (
    select date_trunc('hour', measured_at) as hour, avg(load_mw) as load_mw
    from {{ ref('electricity_load') }}
    group by 1
)
select *
from transit
full join fleet using (hour)
full join air using (hour)
full join punctuality using (hour)
full join grid using (hour)
order by hour
