"""Turn the gold tables into one static HTML page."""

import json
import os
import sys
from pathlib import Path

import duckdb

# One colour scale for the whole page, always paired with words:
# grey = on schedule, yellow -> orange -> red = later and later, blue = ahead of schedule.
PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brussels Hour by Hour</title>
<meta name="description" content="How late STIB runs against its own timetable, stop by stop and hour by hour, with Brussels air quality and Belgian grid load.">
<script src="https://cdn.tailwindcss.com/3.4.16"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
  :root { color-scheme: light; }
  body { background: #f8fafc; }
  .tiles { filter: grayscale(1) contrast(.9) brightness(1.04); }
  .leaflet-tooltip { font: 13px/1.45 ui-sans-serif, system-ui, sans-serif; border-radius: 8px; border: 1px solid #e2e8f0; box-shadow: 0 4px 12px rgba(15,23,42,.08); }
  .range[aria-pressed="true"] { background: #0f172a; color: #fff; }
</style>
</head>
<body class="font-sans text-slate-900 antialiased">
<main class="max-w-6xl mx-auto px-4 py-8 sm:py-10 space-y-6">

  <header class="flex flex-wrap items-end justify-between gap-4">
    <div>
      <p class="text-sm font-medium text-slate-500">Brussels open-data lakehouse</p>
      <h1 class="text-3xl sm:text-4xl font-bold tracking-tight mt-1">Is STIB on time?</h1>
      <p class="text-slate-600 mt-2 max-w-2xl">Every 5 minutes this page's pipeline records when the next metro, tram and bus will arrive at about 900 Brussels stops, and compares that with the official timetable.</p>
    </div>
    <p class="text-sm text-slate-500" id="fresh"></p>
  </header>

  <!-- Right now -->
  <section class="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8 grid lg:grid-cols-[1.2fr_1fr] gap-8">
    <div>
      <p class="text-sm font-semibold text-slate-500 uppercase tracking-wide">Right now</p>
      <p class="text-3xl sm:text-4xl font-bold leading-tight mt-3" id="headline">–</p>
      <p class="text-slate-600 mt-3 text-lg" id="detail"></p>
    </div>
    <div class="grid grid-cols-3 gap-3" id="modes"></div>
    <div class="lg:col-span-2 grid sm:grid-cols-3 gap-3 pt-6 border-t border-slate-100" id="extras"></div>
  </section>

  <!-- Legend, shared by every chart and the map -->
  <section class="bg-white rounded-2xl border border-slate-200 px-6 py-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
    <span class="font-semibold">Colour key</span>
    <span class="text-slate-500">minutes longer than the timetable promises:</span>
    <span id="key" class="flex flex-wrap gap-x-5 gap-y-2"></span>
  </section>

  <!-- Hour by hour, one chart per mode -->
  <section class="bg-white rounded-2xl border border-slate-200 p-6">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h2 class="text-xl font-semibold">Hour by hour</h2>
        <p class="text-slate-600 mt-1">Each bar is one hour. Taller bar = longer extra wait. Bars below the line mean vehicles came sooner than scheduled.</p>
      </div>
      <div class="inline-flex rounded-lg border border-slate-200 p-1 text-sm" role="group" aria-label="Time range">
        <button class="range px-3 py-1.5 rounded-md font-medium text-slate-600" data-h="24" aria-pressed="false">Last 24 h</button>
        <button class="range px-3 py-1.5 rounded-md font-medium text-slate-600" data-h="72" aria-pressed="true">3 days</button>
        <button class="range px-3 py-1.5 rounded-md font-medium text-slate-600" data-h="336" aria-pressed="false">14 days</button>
      </div>
    </div>
    <div class="grid md:grid-cols-3 gap-6 mt-6">
      <div class="min-w-0"><h3 class="font-semibold">Metro</h3><div class="relative h-56 mt-2"><canvas id="c-metro"></canvas></div></div>
      <div class="min-w-0"><h3 class="font-semibold">Tram</h3><div class="relative h-56 mt-2"><canvas id="c-tram"></canvas></div></div>
      <div class="min-w-0"><h3 class="font-semibold">Bus</h3><div class="relative h-56 mt-2"><canvas id="c-bus"></canvas></div></div>
    </div>
  </section>

  <!-- Typical day -->
  <section class="bg-white rounded-2xl border border-slate-200 p-6">
    <h2 class="text-xl font-semibold">When in the day is it worst?</h2>
    <p class="text-slate-600 mt-1">All lines together, by hour of the day (Brussels time), over every day collected so far.</p>
    <div class="relative h-64 mt-4"><canvas id="c-day"></canvas></div>
  </section>

  <!-- Map and lines: click a line to see its stops -->
  <section class="grid lg:grid-cols-[1.6fr_1fr] gap-6">
    <div class="bg-white rounded-2xl border border-slate-200 p-6 min-w-0">
      <h2 class="text-xl font-semibold" id="map-title">Where is it worst?</h2>
      <p class="text-slate-600 mt-1" id="map-sub">Every dot is a stop, coloured by its typical extra wait. Pick a line on the right to see only its stops.</p>
      <div id="map" class="h-[420px] lg:h-[720px] rounded-xl mt-4 bg-slate-100"></div>
    </div>
    <div class="bg-white rounded-2xl border border-slate-200 p-6 min-w-0">
      <div id="overview">
        <h2 class="text-xl font-semibold">Which lines?</h2>
        <p class="text-slate-600 mt-1">Typical extra wait per line. Click a line to see which of its stops are late.</p>
        <label for="linepick" class="block text-sm font-medium text-slate-700 mt-4">Find any line</label>
        <select id="linepick" class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900">
          <option value="">Choose a line…</option>
        </select>
        <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mt-6 mb-1">Most behind schedule</h3>
        <ul id="worst" class="divide-y divide-slate-100"></ul>
        <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mt-6 mb-1">Closest to schedule</h3>
        <ul id="best" class="divide-y divide-slate-100"></ul>
      </div>
      <div id="line-detail" hidden>
        <button id="back" class="text-sm font-medium text-slate-600 hover:text-slate-900 rounded focus:outline-none focus:ring-2 focus:ring-slate-900">← All lines</button>
        <div class="flex items-center gap-3 mt-4" id="detail-head"></div>
        <p class="text-slate-600 mt-3" id="detail-sub"></p>
        <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mt-6 mb-1">Stops, most delayed first</h3>
        <p class="text-xs text-slate-500 mb-2">Click a stop to find it on the map. A stop listed twice has one platform per direction.</p>
        <ol id="detail-stops" class="divide-y divide-slate-100 max-h-[480px] overflow-y-auto"></ol>
      </div>
    </div>
  </section>

  <!-- Air and grid -->
  <section class="grid lg:grid-cols-2 gap-6">
    <div class="bg-white rounded-2xl border border-slate-200 p-6 min-w-0">
      <h2 class="text-xl font-semibold">Air quality in Brussels</h2>
      <p class="text-slate-600 mt-1">Pollution in µg/m³, average of 13 measuring stations. Below the dashed line is within the WHO daily guideline for NO₂.</p>
      <div class="relative h-64 mt-4"><canvas id="c-air"></canvas></div>
    </div>
    <div class="bg-white rounded-2xl border border-slate-200 p-6 min-w-0">
      <h2 class="text-xl font-semibold">Electricity use in Belgium</h2>
      <p class="text-slate-600 mt-1">Total power demand on the national grid, in megawatts. Elia publishes it about a day late.</p>
      <div class="relative h-64 mt-4"><canvas id="c-grid"></canvas></div>
    </div>
  </section>

  <!-- All the numbers -->
  <section class="bg-white rounded-2xl border border-slate-200 p-6 flex flex-wrap items-center justify-between gap-4">
    <div>
      <h2 class="text-xl font-semibold">All the numbers</h2>
      <p class="text-slate-600 mt-1">Every hour collected so far: extra wait, typical wait, air quality and grid load.</p>
    </div>
    <div class="flex flex-wrap gap-2">
      <button id="open-table" class="rounded-lg bg-slate-900 text-white px-4 py-2 text-sm font-medium hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-2">View hourly data</button>
      <button data-csv class="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-900">Download CSV</button>
    </div>
  </section>

  <!-- About -->
  <section id="about" class="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8">
    <h2 class="text-xl font-semibold">About this project</h2>
    <p class="text-slate-600 mt-2 max-w-3xl">An open-data pipeline that checks how well Brussels public transport keeps to its timetable, built on Azure with dbt. Everything here comes from public sources and is recomputed every hour.</p>
    <div class="grid md:grid-cols-3 gap-8 mt-6 text-sm leading-relaxed text-slate-600">
      <div>
        <h3 class="font-semibold text-slate-900 mb-2">What "extra wait" means</h3>
        <p>If you walk up to a stop at a random moment, how long until the next vehicle? We measure that from STIB's live data, work out the same thing from the official timetable, and show the difference. Transport for London uses this measure ("excess wait time") for frequent services.</p>
      </div>
      <div>
        <h3 class="font-semibold text-slate-900 mb-2">How it works</h3>
        <ol class="list-decimal pl-4 space-y-1.5">
          <li>Every 5 minutes an Azure Function saves STIB's live waiting times for about 900 stops. Air quality (IRCEL) and grid load (Elia) are saved every 15 minutes.</li>
          <li>The raw files land untouched in an Azure data lake.</li>
          <li>dbt cleans them and builds hourly tables, with data tests on every model.</li>
          <li>Every hour GitHub Actions rebuilds this page.</li>
        </ol>
      </div>
      <div>
        <h3 class="font-semibold text-slate-900 mb-2">Limits</h3>
        <ul class="list-disc pl-4 space-y-1.5">
          <li>Arrival times are STIB's own predictions, not measured arrivals.</li>
          <li>About a quarter of stops can't be matched to the timetable and are left out, as are Noctis night buses.</li>
          <li>STIB keeps no history, so the record starts when this pipeline did.</li>
        </ul>
      </div>
    </div>
    <p class="mt-6 pt-4 border-t border-slate-100 text-sm text-slate-500">Data: STIB-MIVB, IRCEL-CELINE, Elia, map © OpenStreetMap contributors ·
      <a class="underline hover:text-slate-900" href="https://github.com/Huntsama/brussels-lakehouse">Source code on GitHub</a></p>
  </section>

  <footer class="pt-2 pb-4 flex flex-col sm:flex-row items-center justify-between gap-2 text-sm text-slate-500">
    <p>Developed by <a class="font-medium text-slate-700 hover:text-slate-900 underline-offset-4 hover:underline" href="https://www.jwds.me">Jawad Shaissah</a> ·
      <a class="hover:text-slate-900 underline-offset-4 hover:underline" href="https://www.jwds.me">jwds.me</a></p>
    <p class="text-xs text-slate-400">Page built <span id="built"></span> · __HOURS__ hours of data since <span id="since"></span></p>
  </footer>
</main>

<dialog id="hourly" class="rounded-2xl p-0 w-[min(1000px,94vw)] backdrop:bg-slate-900/40">
  <div class="flex items-center justify-between gap-4 px-6 py-4 border-b border-slate-200">
    <h2 class="text-lg font-semibold">Hourly data <span class="text-sm font-normal text-slate-500">(Brussels time, newest first)</span></h2>
    <div class="flex gap-2">
      <button data-csv class="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50">Download CSV</button>
      <button id="close-table" class="rounded-lg bg-slate-900 text-white px-3 py-1.5 text-sm font-medium hover:bg-slate-700">Close</button>
    </div>
  </div>
  <div class="max-h-[70vh] overflow-auto"><table class="w-full text-sm tabular-nums" id="table"></table></div>
</dialog>
<script>
const D = __DATA__;
const rows = D.city;
const tz = 'Europe/Brussels';
const fmt = (iso, o) => new Date(iso + 'Z').toLocaleString('en-GB', { timeZone: tz, ...o });
const hm = iso => fmt(iso, { hour: '2-digit', minute: '2-digit' });
const dayHour = iso => fmt(iso, { weekday: 'short', hour: '2-digit', minute: '2-digit' });
const num = (v, d = 1) => v == null ? '–' : v.toLocaleString('en-GB', { maximumFractionDigits: d, minimumFractionDigits: d });
const late = v => v == null ? 'no data' : Math.abs(v) < 0.05 ? 'exactly on schedule'
  : v > 0 ? `${num(v)} min late` : `${num(-v)} min early`;

// One colour scale for the whole page, always paired with words
const BANDS = [
  { hi: -0.5, color: '#3b82f6', word: 'Ahead of schedule', key: 'Early' },
  { hi: 0.5, color: '#cbd5e1', word: 'On schedule', key: 'On time (within ½ min)' },
  { hi: 1.5, color: '#fbbf24', word: 'A little late', key: '½ to 1½ min late' },
  { hi: 3, color: '#f97316', word: 'Late', key: '1½ to 3 min late' },
  { hi: Infinity, color: '#dc2626', word: 'Very late', key: 'Over 3 min late' },
];
const band = v => BANDS.find(b => v < b.hi);
document.getElementById('key').innerHTML = BANDS.map(b =>
  `<span class="inline-flex items-center gap-2"><span class="w-3 h-3 rounded-full" style="background:${b.color}"></span>${b.key}</span>`).join('');

const MODES = [['metro', 'Metro'], ['tram', 'Tram'], ['bus', 'Bus']];
const byMode = {};
D.modes.forEach(x => (byMode[x.mode] ??= {})[x.hour] = x.excess);
const lastOf = k => [...rows].reverse().find(r => r[k] != null);

document.getElementById('fresh').textContent = D.last_snapshot ? `Latest data: ${dayHour(D.last_snapshot)}` : '';
document.getElementById('built').textContent = fmt(D.updated, { dateStyle: 'medium', timeStyle: 'short' });
document.getElementById('since').textContent = rows.length ? fmt(rows[0].hour, { day: 'numeric', month: 'long' }) : '–';

// Right now
(() => {
  const hours = Object.keys(Object.assign({}, ...Object.values(byMode))).sort().reverse();
  const h = hours.find(k => MODES.every(([m]) => byMode[m]?.[k] != null));
  const city = h && rows.find(r => r.hour === h)?.excess_wait_min;
  if (h && city != null) {
    const b = band(city);
    document.getElementById('headline').innerHTML =
      `<span class="inline-block w-4 h-4 rounded-full align-middle mr-2" style="background:${b.color}"></span>${b.word}`;
    document.getElementById('detail').textContent =
      `Between ${hm(h)} and the next hour, people waited ${Math.abs(city) < 0.05 ? 'exactly as long as the timetable promised' : `${num(Math.abs(city))} min ${city > 0 ? 'longer' : 'less'} than the timetable promised`}, at a typical stop.`;
    document.getElementById('modes').innerHTML = MODES.map(([m, name]) => {
      const v = byMode[m][h], mb = band(v);
      return `<div class="rounded-xl border border-slate-200 p-4">
        <p class="text-sm font-medium text-slate-500">${name}</p>
        <p class="text-xl sm:text-2xl font-bold mt-1 tabular-nums whitespace-nowrap">${v > 0.05 ? '+' : ''}${num(v)}<span class="text-base font-medium text-slate-500"> min</span></p>
        <p class="text-sm mt-1 flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-full" style="background:${mb.color}"></span>${mb.word}</p></div>`;
    }).join('');
  }
  const wait = lastOf('median_wait_min'), no2 = lastOf('no2'), load = lastOf('load_mw');
  const tile = (label, value, note) => `<div><p class="text-sm text-slate-500">${label}</p><p class="text-lg font-semibold mt-0.5">${value}</p><p class="text-sm text-slate-500">${note}</p></div>`;
  document.getElementById('extras').innerHTML = [
    wait && tile('Typical wait for the next vehicle', `${num(wait.median_wait_min)} min`, `at ${hm(wait.hour)}`),
    no2 && tile('Air pollution (NO₂)', `${num(no2.no2)} µg/m³`, no2.no2 <= 25 ? '✓ within the WHO guideline' : '⚠ above the WHO guideline'),
    load && tile('Belgian electricity demand', `${load.load_mw.toLocaleString('en-GB')} MW`, `at ${dayHour(load.hour)}`),
  ].filter(Boolean).join('');
})();

// Charts
Chart.defaults.font.family = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';
Chart.defaults.font.size = 12;
Chart.defaults.color = '#64748b';
const tooltip = { backgroundColor: '#0f172a', padding: 10, cornerRadius: 8, titleFont: { weight: '600' }, displayColors: false };
const yTitle = text => ({ display: true, text, color: '#64748b' });
const grid = { color: ctx => ctx.tick.value === 0 ? '#94a3b8' : '#f1f5f9' };
const charts = {};
function make(id, config) { charts[id]?.destroy(); charts[id] = new Chart(document.getElementById(id), config); }

function draw(hours) {
  const last = rows.length ? new Date(rows[rows.length - 1].hour + 'Z') : new Date();
  const view = rows.filter(r => last - new Date(r.hour + 'Z') < hours * 3600e3);
  const labels = view.map(r => dayHour(r.hour));
  // Transit collection started later than air and grid: start these charts at the first transit hour
  const first = view.findIndex(r => MODES.some(([m]) => byMode[m]?.[r.hour] != null));
  const tview = first < 0 ? [] : view.slice(first);
  const tlabels = tview.map(r => dayHour(r.hour));
  const vals = MODES.flatMap(([m]) => tview.map(r => byMode[m]?.[r.hour])).filter(v => v != null);
  const yMin = Math.floor(Math.min(-1, ...vals)), yMax = Math.ceil(Math.max(2, ...vals));

  for (const [m, name] of MODES) {
    const data = tview.map(r => byMode[m]?.[r.hour] ?? null);
    make('c-' + m, {
      type: 'bar',
      data: { labels: tlabels, datasets: [{ data, backgroundColor: data.map(v => v == null ? 'transparent' : band(v).color), borderRadius: 3, borderSkipped: false }] },
      options: {
        maintainAspectRatio: false, animation: false,
        plugins: { legend: { display: false }, tooltip: { ...tooltip, callbacks: { label: c => `${name}: ${late(c.raw)} (${band(c.raw).word.toLowerCase()})` } } },
        scales: {
          x: { grid: { display: false }, ticks: { maxTicksLimit: 4, maxRotation: 0 } },
          y: { min: yMin, max: yMax, grid, border: { display: false }, title: yTitle('min late'), ticks: { stepSize: 1 } },
        },
      },
    });
  }

  const line = (label, k, color, dash = []) => ({ label, data: view.map(r => r[k]), borderColor: color, backgroundColor: color, borderWidth: 2, borderDash: dash, pointRadius: 0, pointHoverRadius: 4, spanGaps: true, tension: 0.3 });
  make('c-air', {
    type: 'line',
    data: { labels, datasets: [line('NO₂', 'no2', '#2563eb'), line('PM10', 'pm10', '#0d9488'), line('PM2.5', 'pm25', '#7c3aed'),
      { label: 'WHO NO₂ guideline', data: view.map(() => 25), borderColor: '#94a3b8', borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0, pointHoverRadius: 0 }] },
    options: {
      maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'top', align: 'start', labels: { usePointStyle: true, pointStyle: 'line', boxWidth: 24, padding: 14, color: '#334155' } },
                 tooltip: { ...tooltip, displayColors: true, callbacks: { label: c => `${c.dataset.label}: ${num(c.raw)} µg/m³` } } },
      scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 6, maxRotation: 0 } },
                y: { min: 0, suggestedMax: 30, grid, border: { display: false }, title: yTitle('µg/m³') } },
    },
  });
  make('c-grid', {
    type: 'line',
    data: { labels, datasets: [{ ...line('Demand', 'load_mw', '#0f172a'), fill: { target: 'origin', above: 'rgba(15,23,42,.05)' } }] },
    options: {
      maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { ...tooltip, callbacks: { label: c => `${c.raw.toLocaleString('en-GB')} MW` } } },
      scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 6, maxRotation: 0 } },
                y: { grid, border: { display: false }, title: yTitle('megawatts'), ticks: { callback: v => v.toLocaleString('en-GB') } } },
    },
  });
}

// Typical day (does not depend on the range)
(() => {
  const by = Object.fromEntries(D.hod.map(h => [h.hod, h.excess]));
  const hours = Array.from({ length: 24 }, (_, h) => h);
  const data = hours.map(h => by[h] ?? null);
  new Chart(document.getElementById('c-day'), {
    type: 'bar',
    data: { labels: hours.map(h => `${String(h).padStart(2, '0')}:00`),
            datasets: [{ data, backgroundColor: data.map(v => v == null ? 'transparent' : band(v).color), borderRadius: 4, borderSkipped: false }] },
    options: {
      maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false }, tooltip: { ...tooltip, callbacks: {
        title: c => `${c[0].label} to ${String((+c[0].label.slice(0, 2) + 1) % 24).padStart(2, '0')}:00`,
        label: c => c.raw == null ? 'No data (night)' : `${late(c.raw)} on average`,
      } } },
      scales: { x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } },
                y: { grid, border: { display: false }, title: yTitle('min late'), suggestedMin: -0.5, suggestedMax: 1 } },
    },
  });
})();

// Lines, with STIB's own line colours
const routes = Object.fromEntries(D.routes.map(r => [r.line_id, r]));
const MODE_WORD = { metro: 'Metro', tram: 'Tram', bus: 'Bus' };
const lineById = Object.fromEntries(D.lines.map(l => [l.line_id, l]));
const stopById = Object.fromEntries(D.stops.map(s => [s.stop_id, s]));
const lineStops = {};
D.line_stops.forEach(x => stopById[x.stop_id] && (lineStops[x.line_id] ??= []).push(x));
const dot = c => `<span class="inline-block w-2.5 h-2.5 rounded-full shrink-0" style="background:${c}"></span>`;
const badge = (id, big) => {
  const r = routes[id] ?? { color: '#0f172a', text_color: '#ffffff' };
  return `<span class="inline-grid place-items-center shrink-0 ${big ? 'min-w-[3.25rem] h-10 text-lg' : 'min-w-[2.5rem] h-7 text-sm'} px-2 rounded-md font-bold" style="background:${r.color};color:${r.text_color}">${id}</span>`;
};
function lineList(id, list) {
  document.getElementById(id).innerHTML = list.map(l => `<li>
    <button data-line="${l.line_id}" class="w-full flex items-center gap-3 py-2.5 px-2 -mx-2 rounded-lg text-left hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-900">
      ${badge(l.line_id)}
      <span class="text-sm text-slate-500 w-12">${MODE_WORD[l.mode] ?? l.mode}</span>
      <span class="flex-1 text-sm font-medium flex items-center gap-1.5">${dot(band(l.excess).color)}${late(l.excess)}</span>
      <span class="text-slate-400" aria-hidden="true">›</span>
    </button></li>`).join('');
}
lineList('worst', D.lines.slice(0, 8));
lineList('best', D.lines.slice(-5).reverse());
const pick = document.getElementById('linepick');
pick.innerHTML += [...D.lines].sort((a, b) => a.line_id.localeCompare(b.line_id, undefined, { numeric: true }))
  .map(l => `<option value="${l.line_id}">${l.line_id} · ${MODE_WORD[l.mode] ?? l.mode} · ${late(l.excess)}</option>`).join('');
pick.onchange = () => pick.value && selectLine(pick.value);

// Map
const HOME = [[50.842, 4.37], 12];
const map = L.map('map', { scrollWheelZoom: false, preferCanvas: true }).setView(...HOME);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap contributors', maxZoom: 19, className: 'tiles' }).addTo(map);
const stopTip = (s, v, lineId) => `<b style="text-transform:capitalize">${s.name.toLowerCase()}</b><br>${lineId ? `Line ${lineId}: ` : ''}${band(v).word}, ${late(v)}<br><span style="color:#64748b">Lines ${s.lines}</span>`;
const baseStyle = s => ({ radius: s.excess >= 0.5 ? 6 : 4, weight: 1, color: '#ffffff', opacity: 1, fillOpacity: 0.95, fillColor: band(s.excess).color });
const markers = {};
[...D.stops].sort((a, b) => a.excess - b.excess).forEach(s => {
  markers[s.stop_id] = L.circleMarker([s.lat, s.lon], baseStyle(s))
    .bindTooltip(stopTip(s, s.excess), { direction: 'top', offset: [0, -4] }).addTo(map);
});

const ui = id => document.getElementById(id);
const MAP_TEXT = [ui('map-title').textContent, ui('map-sub').textContent];
function selectLine(id) {
  const l = lineById[id];
  const list = (lineStops[id] ?? []).slice().sort((a, b) => b.excess - a.excess);
  const on = new Set(list.map(x => x.stop_id));
  for (const [sid, m] of Object.entries(markers)) {
    if (!on.has(sid)) m.setStyle({ radius: 3, opacity: 0, fillOpacity: 0.15, fillColor: '#94a3b8' });
  }
  list.forEach(x => {
    const m = markers[x.stop_id];
    m.setStyle({ radius: 8, weight: 2, color: '#0f172a', opacity: 1, fillOpacity: 1, fillColor: band(x.excess).color });
    m.setTooltipContent(stopTip(stopById[x.stop_id], x.excess, id));
    m.bringToFront();
  });
  if (list.length) map.fitBounds(L.latLngBounds(list.map(x => markers[x.stop_id].getLatLng())), { padding: [40, 40], maxZoom: 15 });

  const lateCount = list.filter(x => x.excess >= 0.5).length;
  ui('map-title').textContent = `Line ${id}, stop by stop`;
  ui('map-sub').textContent = `Only line ${id}'s stops are shown, coloured by how late line ${id} is at each one. Hover a stop for details.`;
  ui('detail-head').innerHTML = `${badge(id, true)}<div><p class="text-lg font-semibold">Line ${id}</p><p class="text-sm text-slate-500">${MODE_WORD[l?.mode] ?? ''}</p></div>`;
  ui('detail-sub').innerHTML = list.length
    ? `Typically <b>${late(l.excess)}</b>. ${lateCount} of its ${list.length} stops are more than ½ min late${list[0].excess >= 0.5 ? `; the worst is <b class="capitalize">${stopById[list[0].stop_id].name.toLowerCase()}</b> (${late(list[0].excess)})` : ''}. In a bad hour (1 in 10) it runs ${late(l.p90)}.`
    : 'Not enough data for this line yet.';
  ui('detail-stops').innerHTML = list.map(x => `<li>
    <button data-stop="${x.stop_id}" class="w-full flex items-center gap-3 py-2 px-2 rounded-lg text-left hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-900">
      ${dot(band(x.excess).color)}
      <span class="flex-1 text-sm capitalize">${stopById[x.stop_id].name.toLowerCase()}</span>
      <span class="text-sm font-medium tabular-nums whitespace-nowrap">${late(x.excess)}</span>
    </button></li>`).join('');
  ui('overview').hidden = true;
  ui('line-detail').hidden = false;
  pick.value = id;
  if (innerWidth < 1024) ui('map').scrollIntoView({ behavior: 'smooth', block: 'center' });
}
function showAll() {
  for (const [sid, m] of Object.entries(markers)) {
    const s = stopById[sid];
    m.setStyle(baseStyle(s));
    m.setTooltipContent(stopTip(s, s.excess));
  }
  // late stops back on top
  Object.values(stopById).sort((a, b) => a.excess - b.excess).forEach(s => markers[s.stop_id].bringToFront());
  map.setView(...HOME);
  [ui('map-title').textContent, ui('map-sub').textContent] = MAP_TEXT;
  ui('overview').hidden = false;
  ui('line-detail').hidden = true;
  pick.value = '';
}
ui('back').onclick = showAll;
document.addEventListener('click', e => {
  const line = e.target.closest('[data-line]');
  if (line) selectLine(line.dataset.line);
  const stop = e.target.closest('[data-stop]');
  if (stop) {
    const m = markers[stop.dataset.stop];
    map.setView(m.getLatLng(), 16);
    m.openTooltip();
    if (innerWidth < 1024) ui('map').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  if (e.target.closest('[data-csv]')) downloadCsv();
});

// Hourly table (in a dialog) and CSV download
const cols = [['hour', 'Hour'], ['excess_wait_min', 'Extra wait (min)'], ['median_wait_min', 'Typical wait (min)'], ['no2', 'NO₂ (µg/m³)'], ['pm10', 'PM10 (µg/m³)'], ['pm25', 'PM2.5 (µg/m³)'], ['load_mw', 'Grid (MW)']];
ui('table').innerHTML =
  '<thead><tr class="text-left text-slate-500">' + cols.map(c => `<th class="sticky top-0 bg-white px-4 py-3 font-medium whitespace-nowrap border-b border-slate-200">${c[1]}</th>`).join('') + '</tr></thead><tbody>' +
  [...rows].reverse().map(r => '<tr class="border-t border-slate-100 hover:bg-slate-50">' + cols.map(([k]) =>
    `<td class="px-4 py-2 whitespace-nowrap">${k === 'hour' ? dayHour(r.hour) : r[k] ?? '–'}</td>`).join('') + '</tr>').join('') + '</tbody>';
const dialog = ui('hourly');
ui('open-table').onclick = () => dialog.showModal();
ui('close-table').onclick = () => dialog.close();
dialog.addEventListener('click', e => { if (e.target === dialog) dialog.close(); });
function downloadCsv() {
  const head = ['hour_utc', ...cols.slice(1).map(c => c[0])];
  const lines = [head.join(','), ...rows.map(r => [r.hour + 'Z', ...cols.slice(1).map(([k]) => r[k] ?? '')].join(','))];
  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(new Blob([lines.join(String.fromCharCode(10))], { type: 'text/csv' })  /* no backslash: PAGE is a Python string */), download: 'brussels-hour-by-hour.csv' });
  a.click();
  URL.revokeObjectURL(a.href);
}

const current = () => +document.querySelector('.range[aria-pressed="true"]').dataset.h;
document.querySelectorAll('.range').forEach(b => b.onclick = () => {
  document.querySelectorAll('.range').forEach(x => x.setAttribute('aria-pressed', x === b));
  draw(current());
});
draw(current());
</script>
</body>
</html>
"""

# Night buses (N lines) run every 30-60 min and the measure breaks on gaps that long, so they are left out.
QUERIES = {
    "city": """
        select strftime(hour at time zone 'UTC', '%Y-%m-%dT%H:%M') as hour,
               round(median_wait_min::double, 1) as median_wait_min,
               round(excess_wait_min::double, 1) as excess_wait_min,
               round(no2::double, 1) as no2, round(pm10::double, 1) as pm10,
               round(pm25::double, 1) as pm25, round(load_mw::double) as load_mw
        from main_gold.city_hourly
        where hour >= now() - interval 14 day
        order by hour
    """,
    "modes": """
        select strftime(hour at time zone 'UTC', '%Y-%m-%dT%H:%M') as hour, mode,
               round(median(excess_wait_min), 2) as excess
        from main_gold.stop_line_hourly
        where hour >= now() - interval 14 day and line_id not like 'N%'
        group by all having count(*) >= 50  -- ponytail: drops thin night hours that spike on a handful of stops
        order by hour
    """,
    "hod": """
        select hour(hour at time zone 'Europe/Brussels') as hod, round(median(excess_wait_min), 2) as excess
        from main_gold.stop_line_hourly
        where line_id not like 'N%'
        group by 1 order by 1
    """,
    # ponytail: 30 stop-hours keeps one-off lines out; raise once weeks of data exist
    "lines": """
        select line_id, mode, round(median(excess_wait_min), 2) as excess,
               round(quantile_cont(excess_wait_min, 0.9), 2) as p90, count(*) as n
        from main_gold.stop_line_hourly
        where line_id not like 'N%'
        group by all having count(*) >= 30
        order by excess desc
    """,
    "stops": """
        select g.stop_id, any_value(s.name_fr) as name, any_value(s.lat) as lat, any_value(s.lon) as lon,
               round(median(g.excess_wait_min), 2) as excess, count(*) as n,
               string_agg(distinct g.line_id, ', ' order by g.line_id) as lines
        from main_gold.stop_line_hourly g
        join main_silver.stib_stops s using (stop_id)
        where s.lat is not null and g.line_id not like 'N%'
        group by g.stop_id having count(*) >= 3
    """,
    "line_stops": """
        select line_id, stop_id, round(median(excess_wait_min), 2) as excess, count(*) as n
        from main_gold.stop_line_hourly
        where line_id not like 'N%'
        group by all having count(*) >= 3
    """,
    "routes": "select line_id, color, text_color from main_silver.gtfs_routes",
}


def build(db_path, out_path):
    con = duckdb.connect(db_path, read_only=True)
    data = {}
    for key, sql in QUERIES.items():
        rel = con.sql(sql)
        data[key] = [dict(zip(rel.columns, r)) for r in rel.fetchall()]
    data["updated"] = con.sql("select strftime(now() at time zone 'UTC', '%Y-%m-%dT%H:%M')").fetchone()[0]
    # fetched_at is a plain timestamp already in UTC; casting it would read it as local time
    data["last_snapshot"] = con.sql("select strftime(max(fetched_at), '%Y-%m-%dT%H:%M') from main_silver.stib_waiting").fetchone()[0]
    html = (PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":"), default=float))
                .replace("__HOURS__", str(len(data["city"]))))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html)
    return len(data["city"])


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "site/index.html"
    print(build(os.environ.get("DUCKDB_PATH", "data/lakehouse.duckdb"), out), "hours ->", out)
