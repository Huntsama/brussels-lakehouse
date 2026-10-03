# STIB: what the API gives us

- Open data at data.belgianmobility.io, no API key needed.
- `rt/WaitingTimes`: next arrivals per stop and line, for ~900 stops.
- `rt/VehiclePositions`: each vehicle as a distance from its last stop. No GPS.
- `static/StopDetails`: 2,458 stops with coordinates.
- Catch: `passingtimes` and `vehiclepositions` are JSON *strings* inside the JSON,
  so they need a second parse (`from_json` in DuckDB).
- Real time only, no history endpoint. If we want history, we have to snapshot it ourselves
  every 15 minutes and keep the raw files.
