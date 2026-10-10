"""Turn the gold table into one static HTML page (for jwds.me)."""

import json
import os
import sys
from pathlib import Path

import duckdb

PAGE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brussels hour by hour</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  body { font: 16px/1.5 system-ui, sans-serif; max-width: 900px; margin: 0 auto; padding: 16px; color: #1a1a1a; background: #fff; }
  @media (prefers-color-scheme: dark) { body { color: #eee; background: #121212; } }
  .chart { position: relative; height: 260px; margin-bottom: 32px; }
  small { opacity: .7; }
</style>
<h1>Brussels, hour by hour</h1>
<p>STIB waiting times, air quality and Belgian grid load, collected every 15 minutes.
<br><small>Updated __UPDATED__ UTC · __ROWS__ hours of data · <a href="https://github.com/Huntsama/brussels-lakehouse">code</a></small></p>
<h2>Median wait for the next tram or bus (min)</h2><div class="chart"><canvas id="wait"></canvas></div>
<h2>Excess wait: minutes longer than the timetable promises</h2><div class="chart"><canvas id="ewt"></canvas></div>
<h2>Air: NO₂, PM10, PM2.5 (µg/m³)</h2><div class="chart"><canvas id="air"></canvas></div>
<h2>Belgian grid load (MW)</h2><div class="chart"><canvas id="grid"></canvas></div>
<script>
const rows = __DATA__;
const hours = rows.map(r => r.hour.slice(5, 16).replace('T', ' '));
const line = (id, series) => new Chart(document.getElementById(id), {
  type: 'line',
  data: { labels: hours, datasets: series.map(([key, label]) => ({ label, data: rows.map(r => r[key]), spanGaps: true, pointRadius: rows.length < 48 ? 3 : 0 })) },
  options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false } },
});
line('wait', [['median_wait_min', 'median wait']]);
line('ewt', [['excess_wait_min', 'excess wait (median stop/line)']]);
line('air', [['no2', 'NO₂'], ['pm10', 'PM10'], ['pm25', 'PM2.5']]);
line('grid', [['load_mw', 'load']]);
</script>
</html>
"""


def build(db_path, out_path):
    con = duckdb.connect(db_path, read_only=True)
    rows = con.sql("""
        select strftime(hour at time zone 'UTC', '%Y-%m-%dT%H:%M') as hour,
               round(median_wait_min::double, 1) as median_wait_min,
               round(excess_wait_min::double, 1) as excess_wait_min,
               round(no2::double, 1) as no2, round(pm10::double, 1) as pm10,
               round(pm25::double, 1) as pm25, round(load_mw::double) as load_mw
        from main_gold.city_hourly
        where hour >= now() - interval 14 day
        order by hour
    """).fetchall()
    cols = ["hour", "median_wait_min", "excess_wait_min", "no2", "pm10", "pm25", "load_mw"]
    data = [dict(zip(cols, r)) for r in rows]
    updated = con.sql("select strftime(now() at time zone 'UTC', '%Y-%m-%d %H:%M')").fetchone()[0]
    html = (PAGE.replace("__DATA__", json.dumps(data))
                .replace("__ROWS__", str(len(data)))
                .replace("__UPDATED__", updated))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html)
    return len(data)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "site/index.html"
    print(build(os.environ.get("DUCKDB_PATH", "data/lakehouse.duckdb"), out), "hours ->", out)
