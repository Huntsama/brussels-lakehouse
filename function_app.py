"""Azure Function: save snapshots to the data lake, STIB every 5 minutes, air and grid every 15."""

import os
from datetime import datetime, timezone

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.storage.blob import ContainerClient

from lakehouse import ingest

app = func.FunctionApp()


def blob_writer():
    # Managed identity, no keys in app settings.
    container = ContainerClient(
        f"https://{os.environ['LAKE_ACCOUNT']}.blob.core.windows.net",
        "bronze",
        credential=DefaultAzureCredential(),
    )

    def write(key, text):
        container.upload_blob(key, text, overwrite=True)
        return f"bronze/{key}"

    return write


def snapshot(sources):
    failed = ingest.run(blob_writer(), sources)
    if failed:
        raise RuntimeError(f"sources failed: {failed}")


@app.timer_trigger(arg_name="timer", schedule="0 */5 * * * *")
def stib(timer: func.TimerRequest) -> None:
    snapshot(ingest.STIB_SOURCES)


@app.timer_trigger(arg_name="timer", schedule="0 */15 * * * *")
def air_and_grid(timer: func.TimerRequest) -> None:
    snapshot(ingest.SLOW_SOURCES)


@app.timer_trigger(arg_name="timer", schedule="0 0 3 * * 1")  # Mondays 03:00 UTC
def weekly(timer: func.TimerRequest) -> None:
    now = datetime.now(timezone.utc)
    ingest.save(blob_writer(), "stib_stops", ingest.stib_stops(), now)
    ingest.save_gtfs(blob_writer(), now)
