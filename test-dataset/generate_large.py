"""Generates a realistically large, realistically messy pair of NetSuite-shaped
exports, so the engine can be exercised at a size a real client account would
produce rather than the hand-made 8-row sample.

Deterministic: the seed is fixed, so a run is reproducible and a regression can
be traced to a code change rather than to different data. The output is
gitignored — regenerate it rather than committing tens of megabytes.

    uv run python test-dataset/generate_large.py            # 5,000 transactions
    uv run python test-dataset/generate_large.py 25000      # bigger
"""

import csv
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

SEED = 20260902
OUT_DIR = Path(__file__).parent / "large"

ENTITIES = [
    f"{name} {suffix}"
    for name in (
        "Northwind Trading", "Contoso Manufacturing", "Fabrikam Logistics", "Tailspin Toys",
        "Adventure Works", "Wingtip Couriers", "Litware Systems", "Proseware Medical",
        "Fourth Coffee", "Graphic Design Institute", "Humongous Insurance", "Lucerne Publishing",
        "Trey Research", "Woodgrove Bank", "Alpine Ski House", "Blue Yonder Airlines",
    )
    for suffix in ("Ltd", "Inc", "GmbH")
]

ACCOUNTS = [
    "4000 - Product Revenue", "4010 - Service Revenue", "4020 - Subscription Revenue",
    "4030 - Professional Services", "2100 - Deferred Revenue", "2000 - Accounts Payable",
    "1200 - Accounts Receivable", "5000 - Cost of Goods Sold", "6100 - Travel",
    "6200 - Software Licences", "6300 - Contractors", "6400 - Marketing",
]

TXN_TYPES = ["Invoice", "Bill", "Journal", "Credit Memo", "Customer Payment", "Vendor Bill"]
USERS = [
    "jsmith", "mchen", "alopez", "dpatel", "kowusu", "rnakamura",
    "tbergstrom", "sfernandez", "hmwangi", "lgarcia", "pkoshy", "bosei",
]
# Weighted so most changes are ordinary user edits and automation is the
# minority — an account where everything is System tells you nothing.
ACTORS = USERS * 4 + ["System"] * 5
CONTEXTS = ["UI"] * 6 + ["WEBSERVICES", "SCHEDULED", "CSVIMPORT", "WORKFLOW", "USEREVENT"]

CHANGE_FIELDS = [
    "Amount", "Account", "Status", "Memo", "Department", "Class",
    "Location", "Due Date", "Terms", "Subsidiary",
]
STATUSES = ["Pending Approval", "Approved", "Rejected", "Open", "Paid In Full", "Closed"]
DEPARTMENTS = ["Sales", "Services", "Finance", "Operations", "Marketing", "Engineering"]
CLASSES = ["Direct", "Channel", "Internal", "Reseller"]
LOCATIONS = ["London", "New York", "Bangalore", "Berlin", "Singapore", "Toronto"]
TERMS = ["Net 15", "Net 30", "Net 60", "Due on receipt"]


def _money(rng: random.Random) -> str:
    return f"{rng.uniform(50, 250000):.2f}"


def _value_for(field: str, rng: random.Random) -> str:
    if field == "Amount":
        return _money(rng)
    if field == "Account":
        return rng.choice(ACCOUNTS)
    if field == "Status":
        return rng.choice(STATUSES)
    if field == "Memo":
        return rng.choice(
            ["Q3 retainer", "Migration phase 2", "Annual renewal", "Freight recharge",
             "Support overage", "Change order", "Goodwill credit", "True-up"]
        )
    if field == "Department":
        return rng.choice(DEPARTMENTS)
    if field == "Class":
        return rng.choice(CLASSES)
    if field == "Location":
        return rng.choice(LOCATIONS)
    if field == "Terms":
        return rng.choice(TERMS)
    if field == "Subsidiary":
        return rng.choice(["UK Ltd", "US Inc", "DE GmbH"])
    return (datetime(2026, 1, 1) + timedelta(days=rng.randint(0, 240))).strftime("%m/%d/%Y")


def generate(transaction_count: int) -> tuple[Path, Path]:
    rng = random.Random(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 2, 8, 0)

    transactions_path = OUT_DIR / "large_transactions.csv"
    notes_path = OUT_DIR / "large_system_notes.csv"

    internal_ids = [str(100000 + i) for i in range(transaction_count)]
    dates = {
        internal_id: start + timedelta(minutes=rng.randint(0, 240 * 24 * 60))
        for internal_id in internal_ids
    }

    with transactions_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["Internal ID", "Date", "Type", "Name", "Amount", "Account", "Memo",
             "Created By", "Subsidiary", "Currency"]
        )
        for internal_id in internal_ids:
            roll = rng.random()
            if roll < 0.004:
                writer.writerow([])  # blank row
                continue
            writer.writerow([
                "" if roll < 0.010 else internal_id,  # ~0.6% with no identifying ID
                "not a date" if roll < 0.020 else dates[internal_id].strftime("%m/%d/%Y"),
                rng.choice(TXN_TYPES),
                rng.choice(ENTITIES),
                "" if roll < 0.030 else _money(rng),
                rng.choice(ACCOUNTS),
                _value_for("Memo", rng),
                "" if roll < 0.045 else rng.choice(USERS),
                rng.choice(["UK Ltd", "US Inc", "DE GmbH"]),
                rng.choice(["GBP", "USD", "EUR"]),
            ])

    note_rows = 0
    with notes_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["Internal ID", "Record Type", "Date", "Field", "Old Value", "New Value",
             "Set By", "Context", "Type"]
        )
        for internal_id in internal_ids:
            # Most records carry a handful of changes; a long tail carries many,
            # which is what a heavily automated account actually looks like.
            change_count = rng.choice([0, 1, 2, 2, 3, 3, 4, 5, 6, 9, 14])
            when = dates[internal_id]
            for _ in range(change_count):
                field = rng.choice(CHANGE_FIELDS)
                when = when + timedelta(minutes=rng.randint(1, 600))
                roll = rng.random()
                writer.writerow([
                    internal_id,
                    rng.choice(TXN_TYPES),
                    "not a date" if roll < 0.02 else when.strftime("%m/%d/%Y %H:%M"),
                    field,
                    "" if roll < 0.12 else _value_for(field, rng),  # 12% first-population
                    _value_for(field, rng),
                    "" if roll < 0.05 else rng.choice(ACTORS),
                    rng.choice(CONTEXTS),
                    rng.choice(["Change", "Set", "Create"]),
                ])
                note_rows += 1

    print(f"transactions: {transaction_count:,} rows -> {transactions_path}")
    print(f"system notes: {note_rows:,} rows -> {notes_path}")
    return transactions_path, notes_path


if __name__ == "__main__":
    generate(int(sys.argv[1]) if len(sys.argv) > 1 else 5000)
