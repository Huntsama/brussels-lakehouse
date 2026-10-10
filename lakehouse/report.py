"""Turn the gold table into one static HTML page."""

import json
import os
import sys
from pathlib import Path

import duckdb

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brussels Hour by Hour</title>
<script src="https://cdn.tailwindcss.com/3.4.16"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root { --bg: #f6f6f4; --card: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --line: #e4e3df;
          --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) { --bg: #111110; --card: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --line: #2c2c2a;
                                      --s1: #3987e5; --s2: #d95926; --s3: #199e70; }
  }
  :root[data-theme="dark"] { --bg: #111110; --card: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --line: #2c2c2a;
                             --s1: #3987e5; --s2: #d95926; --s3: #199e70; }
  body { background: var(--bg); color: var(--ink); }
  .card { background: var(--card); border: 1px solid var(--line); }
  .muted { color: var(--ink-2); }
  .range[aria-pressed="true"] { background: var(--ink); color: var(--card); }
</style>
</head>
<body class="font-sans antialiased">
<main class="max-w-6xl mx-auto px-4 py-8 space-y-6">
  <header class="flex flex-wrap items-end justify-between gap-4">
    <div>
      <h1 class="text-2xl sm:text-3xl font-semibold tracking-tight">Brussels, hour by hour</h1>
      <p class="muted mt-1">STIB waiting times, air quality and Belgian grid load, collected every 15 minutes.</p>
    </div>
    <div class="card rounded-lg p-1 flex text-sm" role="group" aria-label="Time range">
      <button class="range px-3 py-1.5 rounded-md" data-h="24" aria-pressed="true">24 h</button>
      <button class="range px-3 py-1.5 rounded-md" data-h="72" aria-pressed="false">3 days</button>
      <button class="range px-3 py-1.5 rounded-md" data-h="336" aria-pressed="false">14 days</button>
    </div>
  </header>

  <section class="grid grid-cols-2 lg:grid-cols-4 gap-4" id="kpis"></section>

  <section class="grid lg:grid-cols-2 gap-4">
    <article class="card rounded-xl p-5 min-w-0">
      <h2 class="font-medium">Median wait for the next tram, bus or metro</h2>
      <p class="muted text-sm">minutes, across all stops</p>
      <div class="relative h-64 mt-3"><canvas id="wait"></canvas></div>
    </article>
    <article class="card rounded-xl p-5 min-w-0">
      <h2 class="font-medium">Excess wait vs the timetable</h2>
      <p class="muted text-sm">minutes longer than promised (median stop and line); 0 = on schedule</p>
      <div class="relative h-64 mt-3"><canvas id="ewt"></canvas></div>
    </article>
    <article class="card rounded-xl p-5 min-w-0">
      <h2 class="font-medium">Air quality</h2>
      <p class="muted text-sm">µg/m³, mean of Brussels stations</p>
      <div class="relative h-64 mt-3"><canvas id="air"></canvas></div>
    </article>
    <article class="card rounded-xl p-5 min-w-0">
      <h2 class="font-medium">Belgian grid load</h2>
      <p class="muted text-sm">MW</p>
      <div class="relative h-64 mt-3"><canvas id="grid"></canvas></div>
    </article>
  </section>

  <details class="card rounded-xl p-5">
    <summary class="cursor-pointer font-medium">Data table</summary>
    <div class="overflow-x-auto mt-3"><table class="w-full text-sm tabular-nums" id="table"></table></div>
  </details>

  <footer class="muted text-sm">Updated <span id="updated"></span> · __ROWS__ hours of data ·
    <a class="underline" href="https://github.com/Huntsama/brussels-lakehouse">code</a></footer>
</main>
<script>
const rows = __DATA__;
const tz = 'Europe/Brussels';
const fmt = (iso, o) => new Date(iso + 'Z').toLocaleString('en-GB', { timeZone: tz, ...o });
const label = iso => fmt(iso, { weekday: 'short', hour: '2-digit', minute: '2-digit' });
document.getElementById('updated').textContent = fmt('__UPDATED__', { dateStyle: 'medium', timeStyle: 'short' });
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

const SERIES = {
  wait: [['median_wait_min', 'Median wait', '--s1']],
  ewt:  [['excess_wait_min', 'Excess wait', '--s1']],
  air:  [['no2', 'NO₂', '--s1'], ['pm10', 'PM10', '--s2'], ['pm25', 'PM2.5', '--s3']],
  grid: [['load_mw', 'Load', '--s1']],
};
const charts = {};

function draw(hours) {
  const last = rows.length ? new Date(rows[rows.length - 1].hour + 'Z') : new Date();
  const view = rows.filter(r => last - new Date(r.hour + 'Z') < hours * 3600e3);
  Chart.defaults.color = css('--ink-2');
  Chart.defaults.font.family = 'ui-sans-serif, system-ui, sans-serif';
  for (const [id, series] of Object.entries(SERIES)) {
    charts[id]?.destroy();
    charts[id] = new Chart(document.getElementById(id), {
      type: 'line',
      data: { labels: view.map(r => label(r.hour)), datasets: series.map(([k, name, c]) => ({
        label: name, data: view.map(r => r[k]), borderColor: css(c), backgroundColor: css(c),
        borderWidth: 2, cubicInterpolationMode: 'monotone', spanGaps: true,
        pointRadius: view.length < 48 ? 3 : 0, pointHoverRadius: 5 })) },
      options: {
        maintainAspectRatio: false, animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: series.length > 1, align: 'start', labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } },
                   tooltip: { backgroundColor: css('--card'), titleColor: css('--ink'), bodyColor: css('--ink'),
                              borderColor: css('--line'), borderWidth: 1, padding: 10 } },
        scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 6, maxRotation: 0 } },
                  y: { grid: { color: css('--line') }, border: { display: false }, beginAtZero: id !== 'grid' } },
      },
    });
  }
}

// KPI tiles: latest value per measure, and the change against 24 h earlier
const latest = k => [...rows].reverse().find(r => r[k] != null);
const KPIS = [['median_wait_min', 'Median wait', 'min'], ['excess_wait_min', 'Excess wait', 'min'],
              ['no2', 'NO₂', 'µg/m³'], ['load_mw', 'Grid load', 'MW']];
document.getElementById('kpis').innerHTML = KPIS.map(([k, name, unit]) => {
  const r = latest(k);
  if (!r) return '';
  const ago = x => (new Date(r.hour + 'Z') - new Date(x.hour + 'Z')) / 3600e3;
  const before = rows.find(x => x[k] != null && ago(x) <= 24);
  const d = before && ago(before) >= 20 ? r[k] - before[k] : null;
  const delta = d == null ? '' : `<span class="muted text-sm">${d > 0 ? '▲' : d < 0 ? '▼' : '•'} ${Math.abs(d).toLocaleString('en-GB', { maximumFractionDigits: 1 })} vs 24 h ago</span>`;
  return `<div class="card rounded-xl p-4">
    <div class="muted text-sm">${name}</div>
    <div class="text-2xl sm:text-3xl font-semibold tabular-nums mt-1">${r[k].toLocaleString('en-GB')} <span class="text-base font-normal muted">${unit}</span></div>
    ${delta}<div class="muted text-xs mt-1">at ${fmt(r.hour, { hour: '2-digit', minute: '2-digit' })}</div></div>`;
}).join('');

const cols = ['hour', 'median_wait_min', 'excess_wait_min', 'no2', 'pm10', 'pm25', 'load_mw'];
document.getElementById('table').innerHTML =
  '<tr class="text-left muted">' + ['Hour', 'Wait', 'Excess', 'NO₂', 'PM10', 'PM2.5', 'Load MW'].map(h => `<th class="py-1 pr-4 font-normal">${h}</th>`).join('') + '</tr>' +
  [...rows].reverse().map(r => '<tr style="border-top:1px solid var(--line)">' +
    cols.map(c => `<td class="py-1 pr-4">${c === 'hour' ? label(r.hour) : r[c] ?? '–'}</td>`).join('') + '</tr>').join('');

document.querySelectorAll('.range').forEach(b => b.onclick = () => {
  document.querySelectorAll('.range').forEach(x => x.setAttribute('aria-pressed', x === b));
  draw(+b.dataset.h);
});
draw(24);
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () =>
  draw(+document.querySelector('.range[aria-pressed="true"]').dataset.h));
</script>
</body>
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
    updated = con.sql("select strftime(now() at time zone 'UTC', '%Y-%m-%dT%H:%M')").fetchone()[0]
    html = (PAGE.replace("__DATA__", json.dumps(data))
                .replace("__ROWS__", str(len(data)))
                .replace("__UPDATED__", updated))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html)
    return len(data)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "site/index.html"
    print(build(os.environ.get("DUCKDB_PATH", "data/lakehouse.duckdb"), out), "hours ->", out)
