"""Fetch current parking availability from the Warsaw open data API and
store the raw response in the bronze bucket. Run by GitHub Actions every
15 minutes; ping_parkings.py is the local equivalent that saves to raw_data/."""

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
    token = os.environ.get(TOKEN_ENV)
    if not token:
        raise SystemExit(f"{TOKEN_ENV} is not set")
    return token


def build_envelope(payload: dict, ingested_at: datetime) -> dict:
    on_github = os.environ.get("GITHUB_ACTIONS") == "true"
    return {
        "source": API_NAME,
        "endpoint": ENDPOINT,
        "ingested_at": ingested_at.isoformat(),
        "collector": "github_actions" if on_github else "local",
        "run_id": os.environ.get("GITHUB_RUN_ID"),
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


def main() -> None:
    creds = {"base_url": BASE_URL, "token": load_token()}
    payload = fetch_parkings(creds)
    ingested_at = datetime.now(timezone.utc)
    body = json.dumps(
        build_envelope(payload, ingested_at), ensure_ascii=False, indent=2
    )
    target = save_to_bucket(body, object_name(ingested_at))

    parkings = payload.get("carParks") or payload.get("Parkings") or []
    print(f"Saved {len(parkings)} parkings to {target}")


if __name__ == "__main__":
    main()
