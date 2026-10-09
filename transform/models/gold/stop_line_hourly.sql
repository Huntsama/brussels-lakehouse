-- Excess Wait Time (EWT), the TfL measure for frequent services:
-- how much longer people really wait than the timetable promises.
-- Actual wait  (AWT): at a random moment, minutes until the next vehicle, averaged over our snapshots.
-- Scheduled wait (SWT): sum(h^2) / (2 * sum(h)) over the timetable headways h in that hour.
with observed as (
    select stop_id, line_id, fetched_at, min(minutes_until) as wait
    from {{ ref('stib_waiting') }}
    where minutes_until between 0 and 60
    group by all
),
awt as (
    select stop_id, line_id, date_trunc('hour', fetched_at::timestamptz) as hour,
           avg(wait) as actual_wait_min, count(*) as snapshots
    from observed
    group by all
),
headways as (
    select stop_id, line_id, scheduled_departure,
           date_diff('second', scheduled_departure,
                     lead(scheduled_departure) over (partition by stop_id, line_id order by scheduled_departure)) / 60.0 as h
    from {{ ref('gtfs_departures') }}
),
swt as (
    select stop_id, line_id, date_trunc('hour', scheduled_departure) as hour,
           sum(h * h) / (2 * sum(h)) as scheduled_wait_min
    from headways
    where h > 0 and h <= 60
    group by all
)
select
    stop_id,
    line_id,
    hour,
    snapshots,
    actual_wait_min,
    scheduled_wait_min,
    actual_wait_min - scheduled_wait_min as excess_wait_min
from awt
join swt using (stop_id, line_id, hour)
