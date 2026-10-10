"""Questions on the gold tables: which modes and lines run late, when, and what moves with it.

    uv run python -m lakehouse.analysis

Correlations need about a week of hourly data before they mean anything; the script says how many hours it used.
"""

import os

import duckdb

MIN_HOURS = 168  # one week
MEASURES = ["median_wait_min", "no2", "pm10", "pm25", "load_mw", "vehicles_avg"]

# Rush hour drives traffic, pollution and power use at once. Subtracting each hour-of-day's mean
# first keeps that daily rhythm from passing for a link between them.
CORRELATIONS = """
    with h as (
        select *, hour(hour at time zone 'Europe/Brussels') as hod
        from main_gold.city_hourly where excess_wait_min is not null
    ),
    d as (select *, """ + ", ".join(f"{c} - avg({c}) over (partition by hod) as {c}_d"
                                  for c in MEASURES + ["excess_wait_min"]) + """ from h)
    """ + "\nunion all\n".join(
    f"select '{c}' as measure, round(corr(excess_wait_min, {c}), 2) as r_raw, "
    f"round(corr(excess_wait_min_d, {c}_d), 2) as r_within_hour, count({c}) as n_hours from d"
    for c in MEASURES)

QUERIES = {
    "Excess wait by mode (minutes longer than the timetable)": """
        select mode,
               round(median(excess_wait_min), 2) as median_excess_min,
               round(median(actual_wait_min), 1) as median_actual_wait_min,
               count(distinct line_id) as lines, sum(snapshots) as observations
        from main_gold.stop_line_hourly
        group by mode order by median_excess_min desc
    """,
    "Worst 15 lines by median excess wait (at least 50 stop-hours)": """
        select line_id, mode,
               round(median(excess_wait_min), 2) as median_excess_min,
               round(quantile_cont(excess_wait_min, 0.9), 2) as p90_excess_min,
               count(*) as stop_hours
        from main_gold.stop_line_hourly
        group by all having count(*) >= 50
        order by median_excess_min desc limit 15
    """,
    "Hour of day profile (Brussels time)": """
        select hour(hour at time zone 'Europe/Brussels') as hour_of_day,
               round(median(excess_wait_min), 2) as median_excess_min,
               round(median(actual_wait_min), 1) as median_actual_wait_min,
               count(distinct hour) as days
        from main_gold.stop_line_hourly
        group by 1 order by 1
    """,
    "Correlation with excess wait (r, raw and with the daily rhythm removed)": CORRELATIONS,
}


def run(db_path):
    con = duckdb.connect(db_path, read_only=True)
    hours = con.sql("select count(*) from main_gold.city_hourly where excess_wait_min is not null").fetchone()[0]
    results = {title: con.sql(sql) for title, sql in QUERIES.items()}
    return hours, results


if __name__ == "__main__":
    hours, results = run(os.environ.get("DUCKDB_PATH", "data/lakehouse.duckdb"))
    print(f"{hours} hours with excess wait data")
    if hours < MIN_HOURS:
        print(f"WARNING: under {MIN_HOURS} hours, treat correlations as noise.")
    for title, rel in results.items():
        print(f"\n## {title}")
        rel.show(max_width=200)
