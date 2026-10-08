# STIB timetable (GTFS)

The live waits only mean something next to what was promised, so we pull the GTFS timetable too.

- Zip of ~19 MB, refreshed weekly. We keep routes, trips, stop_times, calendar and calendar_dates.
- `departure_time` can go past 24:00 (`25:10:00`). Those trips belong to the previous service day,
  so we expand each day as local midnight + seconds and include the day before.
- Service days = `calendar` weekday flags, plus `calendar_dates` additions (type 1), minus removals (type 2).
- Gotcha: our `date=YYYY-MM-DD` folders become a hive column that shadows GTFS's own `date`
  column. Fix: `hive_partitioning = false` and filter on the filename instead.
- About 485k scheduled departures for two service days.
