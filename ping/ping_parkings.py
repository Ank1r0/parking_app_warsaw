"""Fetch current parking availability from the Warsaw open data API
and save the raw response as a timestamped JSON file in raw_data/."""

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRETS_PATH = PROJECT_ROOT / "secret.json"
RAW_DATA_DIR = PROJECT_ROOT / "raw_data"

API_NAME = "warsaw_um"
ENDPOINT = "get_m_parkingi_wolne_miejsca"


def load_secrets(api_name: str) -> dict:
    with open(SECRETS_PATH, encoding="utf-8") as f:
        return json.load(f)[api_name]


def fetch_parkings(creds: dict) -> dict:
    url = f"{creds['base_url']}/{ENDPOINT}"
    response = requests.post(
        url,
        headers={"Authorization": creds["token"]},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def save_raw(payload: dict) -> Path:
    ingested_at = datetime.now(timezone.utc)
    out_dir = RAW_DATA_DIR / ENDPOINT
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{ingested_at:%Y%m%dT%H%M%S}Z.json"

    envelope = {
        "endpoint": ENDPOINT,
        "ingested_at": ingested_at.isoformat(),
        "payload": payload,
    }
    out_path.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_path


def main() -> None:
    creds = load_secrets(API_NAME)
    payload = fetch_parkings(creds)
    out_path = save_raw(payload)

    parkings = payload.get("carParks") or payload.get("Parkings") or []
    print(f"Saved {len(parkings)} parkings to {out_path}")


if __name__ == "__main__":
    main()
