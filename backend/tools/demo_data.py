from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "demo"


def _read_csv(name: str) -> list[dict[str, str]]:
    file_path = DATA_DIR / name
    if not file_path.exists():
        return []

    with file_path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_sales() -> list[dict[str, str]]:
    return _read_csv("sales.csv")


def load_inventory() -> list[dict[str, str]]:
    return _read_csv("inventory.csv")


def load_invoices() -> list[dict[str, str]]:
    return _read_csv("invoices.csv")


def load_customer_enquiries() -> list[dict[str, str]]:
    return _read_csv("customer_enquiries.csv")
