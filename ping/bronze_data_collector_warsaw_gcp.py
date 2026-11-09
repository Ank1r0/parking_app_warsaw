"""Fetch current parking availability from the Warsaw open data API and
store the raw response in the bronze bucket. Runnable as a script, and used
by main.py (the Cloud Run function); ping_parkings.py is the local
equivalent that saves to raw_data/."""

import json
import os
from datetime import datetime, timezone

from google.cloud import storage

from ping_parkings import API_NAME, ENDPOINT, fetch_parkings

BASE_URL = "https://dane.um.warszawa.pl/api/action"
TOKEN_ENV = "WARSAW_UM_TOKEN"

PROJECT_ID = "iva-park"
BUCKET_NAME = "iva_park_bronze"


def load_token() -> str:
    # strip: a token piped into a secret store can carry a trailing newline
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise RuntimeError(f"{TOKEN_ENV} is not set")
    return token


def build_envelope(
    payload: dict, ingested_at: datetime, collector: str, run_id: str | None
) -> dict:
    return {
        "source": API_NAME,
        "endpoint": ENDPOINT,
        "ingested_at": ingested_at.isoformat(),
        "collector": collector,
        "run_id": run_id,
        "payload": payload,
    }


def object_name(ingested_at: datetime) -> str:
    return (
        f"raw/source={API_NAME}/endpoint={ENDPOINT}/"
        f"date={ingested_at:%Y-%m-%d}/{ingested_at:%Y%m%dT%H%M%S}Z.json"
    )


def save_to_bucket(body: str, name: str) -> str:
    client = storage.Client(project=PROJECT_ID)
    blob = client.bucket(BUCKET_NAME).blob(name)
    # if_generation_match=0: fail rather than overwrite an existing snapshot
    blob.upload_from_string(
        body, content_type="application/json", if_generation_match=0
    )
    return f"gs://{BUCKET_NAME}/{name}"


def collect(collector: str, run_id: str | None) -> tuple[int, str]:
    creds = {"base_url": BASE_URL, "token": load_token()}
    payload = fetch_parkings(creds)
    ingested_at = datetime.now(timezone.utc)
    body = json.dumps(
        build_envelope(payload, ingested_at, collector, run_id),
        ensure_ascii=False, indent=2,
    )
    target = save_to_bucket(body, object_name(ingested_at))

    parkings = payload.get("carParks") or payload.get("Parkings") or []
    return len(parkings), target


def main() -> None:
    on_github = os.environ.get("GITHUB_ACTIONS") == "true"
    count, target = collect(
        collector="github_actions" if on_github else "local",
        run_id=os.environ.get("GITHUB_RUN_ID"),
    )
    print(f"Saved {count} parkings to {target}")


if __name__ == "__main__":
    main()
