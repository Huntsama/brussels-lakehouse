import json
from datetime import datetime, timezone

from lakehouse import ingest

NOW = datetime(2026, 10, 10, 8, 15, tzinfo=timezone.utc)


def test_run_writes_partitioned_files(tmp_path):
    failed = ingest.run(tmp_path, {"elia": lambda: {"results": [1]}}, NOW)
    path = tmp_path / "elia" / "date=2026-10-10" / "081500.json"
    assert failed == []
    assert json.loads(path.read_text()) == {"fetched_at": NOW.isoformat(), "data": {"results": [1]}}


def test_one_failing_source_does_not_stop_the_rest(tmp_path):
    def boom():
        raise OSError("api down")

    failed = ingest.run(tmp_path, {"a": boom, "b": lambda: []}, NOW)
    assert failed == ["a"]
    assert (tmp_path / "b" / "date=2026-10-10" / "081500.json").exists()


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
