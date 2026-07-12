"""Build one flat, denormalized dataset (Kaggle-style) from the raw snapshots.

Output: silver/parking_dataset.csv — one row per parking per snapshot, with
every parking attribute flattened into a plain column.
"""

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "raw_data" / "get_m_parkingi_wolne_miejsca"
OUT_PATH = PROJECT_ROOT / "silver" / "parking_dataset.csv"

VEHICLE_KEY = {
    "Samochód osobowy": "car",
    "Samochód dostawczy": "van",
    "Motor": "motorcycle",
}


def vehicle_key(vehicle_type: str) -> str:
    return VEHICLE_KEY.get(
        vehicle_type, vehicle_type.strip().lower().replace(" ", "_")
    )


def flatten_parking(parking: dict) -> dict:
    row = {
        "parking_id": parking["name"].strip().lower().replace(" ", "_"),
        "name": parking["name"].strip(),
        "latitude": float(parking["latitude"]),
        "longitude": float(parking["longitude"]),
        "address": parking.get("adress") or None,  # sic: the API misspells the key
        "category": parking.get("parkingCategory") or None,
        "manager": parking.get("manager") or None,
        "manager_email": parking.get("managerEmail") or None,
        "manager_phone": parking.get("managerTelephone") or None,
        "operator_phone": parking.get("operatorTelephone") or None,
        "payment_methods": parking.get("acceptedPaymentMethod") or None,
        "allowed_vehicles": parking.get("allowedVehicleType") or None,
        "security": parking.get("additionalSecurity") or None,
        "levels": parking.get("levels"),
    }

    totals = {"standard": 0, "disabled": 0, "electric": 0}
    for level in parking.get("total_places", []):
        for kind in totals:
            totals[kind] += int(level.get(kind, 0) or 0)
    row.update({f"total_{k}": v for k, v in totals.items()})

    free = parking.get("free_places_total", {})
    row["free_public"] = free.get("public")
    row["free_disabled"] = free.get("disabled")
    row["free_electric"] = free.get("electric")

    for hours in parking.get("opening_hours") or []:
        for day, value in hours.items():
            row[f"open_{day}"] = value

    for tariff in parking.get("tariffs") or []:
        vk = vehicle_key(tariff.get("VehicleType", ""))
        for price in tariff.get("Prices", []):
            length = int(float(price["StayLength"]))
            row[f"price_{vk}_{length}h"] = float(price["StayPrice"])

    for dim in parking.get("dimensions") or []:
        vk = vehicle_key(dim.get("VehicleType", ""))
        for src_key, col in (("Length", f"max_{vk}_length_m"),
                             ("Width", f"max_{vk}_width_m")):
            value = dim.get(src_key)
            if value not in (None, ""):
                row[col] = float(value)

    return row


def main() -> None:
    rows = []
    for file in sorted(RAW_DIR.glob("*.json")):
        doc = json.loads(file.read_text(encoding="utf-8"))
        payload = doc["payload"]
        for parking in payload["carParks"]:
            row = flatten_parking(parking)
            row["source_ts"] = payload.get("Timestamp")
            row["ingested_at"] = doc["ingested_at"]
            rows.append(row)

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["parking_id", "source_ts"], keep="first")

    lead = ["parking_id", "name", "source_ts", "ingested_at",
            "free_public", "free_disabled", "free_electric",
            "total_standard", "total_disabled", "total_electric"]
    rest = sorted(c for c in df.columns if c not in lead)
    df = df[lead + rest].sort_values(["source_ts", "parking_id"])

    OUT_PATH.parent.mkdir(exist_ok=True)
    # utf-8-sig so Excel renders the Polish characters correctly
    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"{OUT_PATH.name}: {len(df)} rows x {len(df.columns)} columns")
    print(f"snapshots: {df['source_ts'].min()} .. {df['source_ts'].max()}")


if __name__ == "__main__":
    main()
