import gzip
import json
from datetime import datetime, timezone

from lakehouse import ingest

NOW = datetime(2026, 10, 10, 8, 15, tzinfo=timezone.utc)


def test_run_writes_partitioned_files(tmp_path):
    failed = ingest.run(ingest.local_writer(tmp_path), {"elia": lambda: {"results": [1]}}, NOW)
    path = tmp_path / "elia" / "date=2026-10-10" / "081500.json.gz"
    assert failed == []
    assert json.loads(gzip.decompress(path.read_bytes())) == {"fetched_at": NOW.isoformat(), "data": {"results": [1]}}


def test_one_failing_source_does_not_stop_the_rest(tmp_path):
    def boom():
        raise OSError("api down")

    failed = ingest.run(ingest.local_writer(tmp_path), {"a": boom, "b": lambda: []}, NOW)
    assert failed == ["a"]
    assert (tmp_path / "b" / "date=2026-10-10" / "081500.json.gz").exists()


def test_ircel_keeps_only_brussels(monkeypatch):
    def fake(url, params=None):
        if url.endswith("/timeseries"):
            return [
                {"id": "1", "uom": "µg/m³", "station": {"properties": {"label": "41R001 - Molenbeek"},
                                                        "geometry": {"coordinates": [4.3, 50.8, "NaN"]}}},
                {"id": "2", "uom": "µg/m³", "station": {"properties": {"label": "42R842 - Mechelen"},
                                                        "geometry": {"coordinates": [4.4, 51.0, "NaN"]}}},
            ]
        return {"values": [{"timestamp": 0, "value": 5.0}]}

    monkeypatch.setattr(ingest, "get_json", fake)
    rows = ingest.ircel()
    assert {r["station"] for r in rows} == {"41R001 - Molenbeek"}
    assert len(rows) == len(ingest.IRCEL_PHENOMENA)


def test_report_page_has_data(tmp_path):
    import duckdb
    from lakehouse import report

    db = str(tmp_path / "t.duckdb")
    con = duckdb.connect(db)
    con.sql("create schema main_gold")
    con.sql("""create table main_gold.city_hourly as select now()::timestamptz as hour,
               4.5 as median_wait_min, 0.8 as excess_wait_min, 10.0 as no2, 5.0 as pm10, 2.0 as pm25, 8000.0 as load_mw""")
    con.sql("""create table main_gold.stop_line_hourly as select '1' as stop_id, '71' as line_id, 'bus' as mode,
               now()::timestamptz as hour, 4 as snapshots, 6.0 as actual_wait_min, 5.0 as scheduled_wait_min, 1.0 as excess_wait_min""")
    con.sql("create schema main_silver")
    con.sql("create table main_silver.stib_stops as select '1' as stop_id, 'Flagey' as name_fr, 'Flagey' as name_nl, 50.83 as lat, 4.37 as lon")
    con.sql("create table main_silver.gtfs_routes as select '71' as line_id, '#0000FF' as color, '#FFFFFF' as text_color")
    con.sql("create table main_silver.stib_waiting as select now() as fetched_at")
    con.close()
    out = tmp_path / "index.html"
    assert report.build(db, out) == 1
    html = out.read_text()
    assert '"median_wait_min":4.5' in html
    assert '"excess":1.0' in html  # hour-of-day profile, no minimum-count filter
