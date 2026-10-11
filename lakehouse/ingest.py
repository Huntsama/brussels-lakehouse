"""Pull one snapshot of each source and save it untouched (bronze).

Layout: <BRONZE_DIR>/<source>/date=YYYY-MM-DD/<HHMMSS>.json.gz
STIB every 5 minutes, air and grid every 15; STIB is real-time only, so history = our snapshots.
"""

import gzip
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STIB = "https://api-management-discovery-production.azure-api.net/api/datasets/stibmivb"
IRCEL = "https://geo.irceline.be/sos/api/v1"
ELIA = "https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods001/records"

# NO2, PM10, PM2.5
IRCEL_PHENOMENA = {"8": "no2", "5": "pm10", "6001": "pm25"}


def get_json(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "be-open-lakehouse"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def stib_vehicles():
    return get_json(f"{STIB}/rt/VehiclePositions")


def stib_waiting():
    return get_json(f"{STIB}/rt/WaitingTimes")


def stib_stops():
    return get_json(f"{STIB}/static/StopDetails")


GTFS_FILES = ["routes.txt", "trips.txt", "stop_times.txt", "calendar.txt", "calendar_dates.txt"]


def save_gtfs(write, now):
    """STIB timetable (GTFS zip, ~19 MB). Keep the files we model, as published."""
    import io
    import zipfile
    req = urllib.request.Request(STIB.replace("datasets/stibmivb", "gtfs/feed/stibmivb/static"),
                                 headers={"User-Agent": "be-open-lakehouse"})
    with urllib.request.urlopen(req, timeout=300) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    return [write(f"gtfs/date={now:%Y-%m-%d}/{name}", z.read(name).decode("utf-8-sig")) for name in GTFS_FILES]


def ircel(hours=24):
    """Last `hours` of hourly values for every Brussels station (codes start with 41)."""
    end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for ph, name in IRCEL_PHENOMENA.items():
        for ts in get_json(f"{IRCEL}/timeseries", {"phenomenon": ph, "expanded": "true"}):
            station = ts["station"]["properties"]["label"]
            if not station.startswith("41"):
                continue
            data = get_json(f"{IRCEL}/timeseries/{ts['id']}/getData", {"timespan": f"PT{hours}H/{end}"})
            lon, lat = ts["station"]["geometry"]["coordinates"][:2]
            out.append({"timeseries_id": ts["id"], "pollutant": name, "station": station,
                        "lon": lon, "lat": lat, "uom": ts.get("uom"), "values": data["values"]})
    return out


def elia(days=2):
    # 100 rows = 25h of 15-min data, enough for a 15-min schedule; page if run less often
    return get_json(ELIA, {
        "where": f"datetime >= now(days=-{days}) and totalload is not null",
        "select": "datetime,resolutioncode,totalload",
        "order_by": "datetime desc",
        "limit": 100,
    })


# STIB changes minute to minute; IRCEL is hourly and Elia 15-min, so polling those faster adds nothing.
STIB_SOURCES = {"stib_vehicles": stib_vehicles, "stib_waiting": stib_waiting}
SLOW_SOURCES = {"ircel": ircel, "elia": elia}
SOURCES = STIB_SOURCES | SLOW_SOURCES


def local_writer(root):
    def write(key, text):
        path = Path(root) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text) if isinstance(text, bytes) else path.write_text(text)
        return path
    return write


def save(write, source, payload, now):
    # gzip: STIB waiting times are ~0.8 MB of JSON per snapshot, ~10x smaller compressed; DuckDB reads .gz as is
    key = f"{source}/date={now:%Y-%m-%d}/{now:%H%M%S}.json.gz"
    return write(key, gzip.compress(json.dumps({"fetched_at": now.isoformat(), "data": payload}).encode()))


def run(write, sources=SOURCES, now=None):
    now = now or datetime.now(timezone.utc)
    failed = []
    for name, fetch in sources.items():
        try:
            print(save(write, name, fetch(), now))
        except Exception as e:  # one dead API must not lose the others
            print(f"{name} failed: {e}", file=sys.stderr)
            failed.append(name)
    return failed


if __name__ == "__main__":
    write = local_writer(os.environ.get("BRONZE_DIR", "data/bronze"))
    if sys.argv[1:] == ["stops"]:  # static, refresh weekly
        print(save(write, "stib_stops", stib_stops(), datetime.now(timezone.utc)))
    elif sys.argv[1:] == ["gtfs"]:  # timetable, refresh weekly
        print(*save_gtfs(write, datetime.now(timezone.utc)), sep="\n")
    else:
        sys.exit(1 if run(write) else 0)
