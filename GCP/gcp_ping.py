"""Check the connection to the GCS bucket: upload a small test object
under _ping/ and read it back."""

import json
from datetime import datetime, timezone

from google.cloud import storage

PROJECT_ID = "iva-park"
BUCKET_NAME = "iva_park_bronze"
PING_PREFIX = "_ping"


def send_ping(bucket: storage.Bucket) -> tuple[storage.Blob, str]:
    sent_at = datetime.now(timezone.utc)
    blob = bucket.blob(f"{PING_PREFIX}/{sent_at:%Y%m%dT%H%M%S}Z.json")
    body = json.dumps({"ping": "iva_park", "sent_at": sent_at.isoformat()})
    blob.upload_from_string(body, content_type="application/json")
    return blob, body


def main() -> None:
    client = storage.Client(project=PROJECT_ID)
    bucket = client.bucket(BUCKET_NAME)

    blob, body = send_ping(bucket)
    received = blob.download_as_text()
    if received != body:
        raise SystemExit(f"Read back different content from {blob.name}")

    print(f"Ping OK: gs://{BUCKET_NAME}/{blob.name}")


if __name__ == "__main__":
    main()
