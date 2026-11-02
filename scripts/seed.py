"""Create the schema and fill it with deterministic fictional data.

Same seed, same data: the eval suite's reference answers depend on it.
Usage: DATABASE_URL=postgresql://... python scripts/seed.py

The data has three planted stories to investigate:
- Summit Lending stops accepting leads from 15 Aug 2026 (and is now paused).
- BrightPath Media's lead quality drops from 1 Sep 2026: more duplicates and returns.
- RateBridge Exchange cuts its auto-loan bids by 20% from 1 Jun 2026.
"""

import os
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
START = date(2025, 1, 1)
END = date(2026, 10, 31)
END_TS = datetime(2026, 10, 31, 23, 59, 59)

SUMMIT_STOPS = datetime(2026, 8, 15)
BRIGHTPATH_DECLINE = datetime(2026, 9, 1)
RATEBRIDGE_CUT = datetime(2026, 6, 1)
RESTRICTED_FROM = datetime(2026, 5, 1)
PAUSED_FROM = datetime(2026, 7, 1)

PRODUCTS = ["personal_loan", "auto_loan", "debt_relief", "credit_repair"]
PAYOUT_RANGE = {"personal_loan": (18, 30), "auto_loan": (15, 25), "debt_relief": (25, 40), "credit_repair": (6, 10)}
LOAN_RANGE = {"personal_loan": (1000, 35000), "auto_loan": (5000, 60000), "debt_relief": (10000, 80000), "credit_repair": (500, 5000)}
CREDIT_BANDS = ["excellent", "good", "fair", "poor"]
CREDIT_WEIGHTS = [1, 3, 3, 2]
CREDIT_ACCEPT = {"excellent": 1.25, "good": 1.0, "fair": 0.7, "poor": 0.35}
CREDIT_BID = {"excellent": 1.3, "good": 1.0, "fair": 0.8, "poor": 0.55}
STATES = ["CA", "TX", "FL", "NY", "PA", "IL", "OH", "GA", "NC", "MI", "NJ", "VA", "AZ", "WA", "TN"]
STATE_WEIGHTS = [12, 10, 9, 7, 5, 5, 5, 4, 4, 4, 3, 3, 3, 3, 3]
CHANNELS = ["search", "social", "email", "display"]

AFFILIATE_NAMES = [
    "BrightPath Media", "Northstar Digital", "Copperline Leads", "Bluebird Performance", "Redwood Traffic",
    "Lakeshore Media", "Ironclad Digital", "Silverleaf Leads", "Harborview Media", "Tallgrass Digital",
    "Granite Peak Leads", "Sunrise Performance", "Westwind Media", "Evergreen Leads", "Foxglove Digital",
    "Clearwater Media", "Highland Performance", "Juniper Leads", "Magnolia Digital", "Oakridge Media",
    "Pinnacle Traffic", "Quarry Lane Leads", "Riverbend Digital", "Stonebridge Media", "Thistle Performance",
    "Upland Leads", "Vantage Point Media", "Willow Creek Digital", "Yellowstone Leads", "Zephyr Media",
]
# name, type, products bought, base bid per product, base acceptance, mean response ms
BUYERS = [
    ("Summit Lending", "lender", {"personal_loan": 62}, 0.42, 380),
    ("Keystone Credit", "lender", {"personal_loan": 55, "auto_loan": 44}, 0.38, 520),
    ("Harbor Auto Finance", "lender", {"auto_loan": 50}, 0.40, 610),
    ("Pinecrest Loans", "lender", {"personal_loan": 48}, 0.45, 450),
    ("Bluewater Lending", "lender", {"personal_loan": 44, "debt_relief": 70}, 0.35, 700),
    ("Meridian Debt Solutions", "lender", {"debt_relief": 82}, 0.33, 900),
    ("Clearpath Credit Repair", "lender", {"credit_repair": 19}, 0.55, 300),
    ("Fairway Auto Credit", "lender", {"auto_loan": 41}, 0.48, 560),
    ("LoanLink Network", "network", {"personal_loan": 36, "auto_loan": 30, "debt_relief": 55}, 0.60, 1100),
    ("RateBridge Exchange", "network", {"personal_loan": 33, "auto_loan": 38, "credit_repair": 14}, 0.62, 950),
    ("FinMatch Network", "network", {"personal_loan": 30, "debt_relief": 48, "credit_repair": 12}, 0.66, 1250),
]


def build(rng: random.Random) -> dict[str, list[tuple]]:
    rows: dict[str, list[tuple]] = {}

    statuses = ["active"] * 24 + ["restricted"] * 3 + ["paused"] * 3
    rng.shuffle(statuses)
    statuses[0] = "active"  # BrightPath stays active so its decline shows up
    affiliates = []
    for i, name in enumerate(AFFILIATE_NAMES, start=1):
        tier = rng.choices(["gold", "silver", "bronze"], weights=[1, 2, 3])[0]
        affiliates.append((i, name, tier, statuses[i - 1], date(2024, 1, 1) + timedelta(days=rng.randrange(540))))
    rows["affiliates"] = affiliates

    campaigns = []
    for aff in affiliates:
        for _ in range(rng.randint(1, 4)):
            product, channel = rng.choice(PRODUCTS), rng.choice(CHANNELS)
            lo, hi = PAYOUT_RANGE[product]
            campaigns.append((len(campaigns) + 1, aff[0], f"{aff[1].split()[0]} {product.replace('_', ' ').title()} {channel.title()}",
                              channel, product, round(rng.uniform(lo, hi), 2)))
    rows["campaigns"] = campaigns

    rows["buyers"] = [(i, name, btype, "paused" if name == "Summit Lending" else "active")
                      for i, (name, btype, *_rest) in enumerate(BUYERS, start=1)]
    buyer_ids = {b[0]: i for i, b in enumerate(BUYERS, start=1)}

    tier_weight = {"gold": 6, "silver": 3, "bronze": 1}
    aff_by_id = {a[0]: a for a in affiliates}
    campaign_weights = [tier_weight[aff_by_id[c[1]][2]] for c in campaigns]

    leads, pings, sales, returns = [], [], [], []
    day = START
    while day <= END:
        months_in = (day.year - START.year) * 12 + day.month - 1
        volume = int(70 * (1.02 ** months_in) * (0.75 if day.weekday() >= 5 else 1.0) * rng.uniform(0.85, 1.15))
        for _ in range(volume):
            campaign = rng.choices(campaigns, weights=campaign_weights)[0]
            affiliate = aff_by_id[campaign[1]]
            received = datetime.combine(day, datetime.min.time()) + timedelta(seconds=rng.randrange(86400))
            if (affiliate[3] == "restricted" and received >= RESTRICTED_FROM) or (affiliate[3] == "paused" and received >= PAUSED_FROM):
                continue
            declining = affiliate[1] == "BrightPath Media" and received >= BRIGHTPATH_DECLINE
            product = campaign[4]
            band = rng.choices(CREDIT_BANDS, weights=CREDIT_WEIGHTS)[0]
            lead_id = len(leads) + 1
            is_dup = rng.random() < (0.18 if declining else 0.04)
            leads.append((lead_id, campaign[0], received, product, rng.choices(STATES, weights=STATE_WEIGHTS)[0],
                          rng.randrange(*LOAN_RANGE[product], 500), band, is_dup))
            if is_dup:
                continue  # duplicates are filtered before the ping tree

            offers = []
            for name, _type, bids, accept, latency in BUYERS:
                if product not in bids:
                    continue
                bid = bids[product] * CREDIT_BID[band] * rng.uniform(0.9, 1.1)
                if name == "RateBridge Exchange" and product == "auto_loan" and received >= RATEBRIDGE_CUT:
                    bid *= 0.8
                offers.append((round(bid, 2), name, accept, latency))
            offers.sort(reverse=True)

            for position, (bid, name, accept, latency) in enumerate(offers[:5], start=1):
                p_accept = 0.0 if name == "Summit Lending" and received >= SUMMIT_STOPS else min(accept * CREDIT_ACCEPT[band], 0.95)
                accepted = rng.random() < p_accept
                response_ms = max(80, int(rng.gauss(latency, latency * 0.25)))
                pings.append((len(pings) + 1, lead_id, buyer_ids[name], position, bid, accepted, response_ms))
                if not accepted:
                    continue
                sold_at = received + timedelta(milliseconds=response_ms * position)
                sale_id = len(sales) + 1
                sales.append((sale_id, lead_id, buyer_ids[name], sold_at, bid, campaign[5]))
                if rng.random() < (0.30 if declining else 0.06):
                    returned_at = sold_at + timedelta(days=rng.randint(1, 20), hours=rng.randint(0, 23))
                    if returned_at <= END_TS:
                        reason = (rng.choice(["fraud", "invalid_contact"]) if declining
                                  else rng.choices(["invalid_contact", "duplicate", "fraud", "not_interested"], weights=[4, 2, 1, 3])[0])
                        returns.append((len(returns) + 1, sale_id, returned_at, reason))
                break
        day += timedelta(days=1)

    rows.update(leads=leads, pings=pings, sales=sales, returns=returns)
    rows["staff_accounts"] = [(1, "admin@example.com", "$2b$12$fakehashfakehashfakehash", "admin"),
                              (2, "analyst@example.com", "$2b$12$fakehashfakehashfakehash", "analyst")]
    return rows


ID_COLUMNS = {
    "affiliates": "affiliate_id", "campaigns": "campaign_id", "buyers": "buyer_id", "leads": "lead_id",
    "pings": "ping_id", "sales": "sale_id", "returns": "return_id", "staff_accounts": "account_id",
}


def main() -> None:
    rows = build(random.Random(42))
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute((ROOT / "db" / "schema.sql").read_text())
        with conn.cursor() as cur:
            for table, data in rows.items():
                with cur.copy(f"COPY leadflow.{table} FROM STDIN") as copy:
                    for row in data:
                        copy.write_row(row)
                # Explicit ids above, so move each serial past them.
                cur.execute(f"SELECT setval(pg_get_serial_sequence('leadflow.{table}', %s), %s)", (ID_COLUMNS[table], len(data)))
        print({table: len(data) for table, data in rows.items()})


if __name__ == "__main__":
    main()
