"""Read the editable per-100 g food catalog shipped with FitApp."""

import csv
import math
from pathlib import Path


CSV_PATH = Path(__file__).resolve().parent / "data" / "foods.csv"
CSV_FIELDS = ("food", "calories", "protein", "carbs", "fat")


def load_foods():
    foods = []
    names = set()
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CSV_FIELDS:
            raise ValueError(
                f"Food catalog must use exactly these columns: {','.join(CSV_FIELDS)}"
            )
        for line_number, row in enumerate(reader, start=2):
            name = (row.get("food") or "").strip()
            if not name:
                continue
            key = name.casefold()
            if key in names:
                raise ValueError(f"Duplicate food in catalog on line {line_number}: {name}")
            names.add(key)
            try:
                item = {
                    "food": name,
                    "calories": float(row["calories"]),
                    "protein": float(row["protein"]),
                    "carbs": float(row["carbs"]),
                    "fat": float(row["fat"]),
                }
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid nutrition values on catalog line {line_number}") from exc
            if any(
                not math.isfinite(value) or value < 0
                for field, value in item.items()
                if field != "food"
            ):
                raise ValueError(
                    f"Nutrition values must be finite and nonnegative on line {line_number}"
                )
            foods.append(item)
    return foods
