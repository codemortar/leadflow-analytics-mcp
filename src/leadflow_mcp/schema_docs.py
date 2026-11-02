"""Hand-written description of the data, in the business's terms.

The model sees this rather than raw DDL: it carries the rules (what counts as revenue,
margin, acceptance) that table and column names alone don't.
"""

TABLES: dict[str, dict] = {
    "affiliates": {
        "description": "Publishers who send us consumer loan enquiries (leads).",
        "columns": {
            "affiliate_id": "int, primary key",
            "name": "text, e.g. 'BrightPath Media'",
            "tier": "text: 'gold', 'silver' or 'bronze'",
            "status": "text: 'active', 'paused' or 'restricted' (current status)",
            "joined_on": "date",
        },
    },
    "campaigns": {
        "description": "An affiliate's traffic source for one product.",
        "columns": {
            "campaign_id": "int, primary key",
            "affiliate_id": "int, references affiliates",
            "name": "text",
            "channel": "text: 'search', 'social', 'email' or 'display'",
            "product": "text: 'personal_loan', 'auto_loan', 'debt_relief' or 'credit_repair'",
            "payout": "numeric, what we pay the affiliate per sold lead",
        },
    },
    "buyers": {
        "description": "Lenders and networks that buy leads.",
        "columns": {
            "buyer_id": "int, primary key",
            "name": "text, e.g. 'Summit Lending'",
            "buyer_type": "text: 'lender' or 'network'",
            "status": "text: 'active' or 'paused' (current status)",
        },
    },
    "leads": {
        "description": "Every consumer enquiry received. Duplicates are filtered out and never offered to buyers.",
        "columns": {
            "lead_id": "int, primary key",
            "campaign_id": "int, references campaigns",
            "received_at": "timestamp, US Eastern",
            "product": "text, same values as campaigns.product",
            "state": "text, two-letter US state code",
            "loan_amount": "int, dollars requested",
            "credit_band": "text: 'excellent', 'good', 'fair' or 'poor'",
            "is_duplicate": "boolean",
        },
    },
    "pings": {
        "description": "Offers of a lead to buyers. A lead is offered to buyers in turn, highest bid first, until one accepts.",
        "columns": {
            "ping_id": "int, primary key",
            "lead_id": "int, references leads",
            "buyer_id": "int, references buyers",
            "position": "int, 1 for the first buyer offered the lead",
            "bid_price": "numeric, the buyer's price for this lead",
            "accepted": "boolean",
            "response_ms": "int, buyer response time in milliseconds",
        },
    },
    "sales": {
        "description": "Leads sold: one row per sold lead, to the buyer that accepted it.",
        "columns": {
            "sale_id": "int, primary key",
            "lead_id": "int, references leads (unique)",
            "buyer_id": "int, references buyers",
            "sold_at": "timestamp, US Eastern",
            "price": "numeric, what the buyer pays us",
            "affiliate_payout": "numeric, what we pay the affiliate for this lead",
        },
    },
    "returns": {
        "description": "Sold leads a buyer sent back for a refund. Buyers can return a lead up to 20 days after the sale, so the latest weeks are incomplete.",
        "columns": {
            "return_id": "int, primary key",
            "sale_id": "int, references sales (unique)",
            "returned_at": "timestamp, US Eastern",
            "reason": "text: 'invalid_contact', 'duplicate', 'fraud' or 'not_interested'",
        },
    },
}

RULES = """\
Business rules:
- Gross revenue = sum(sales.price). Net revenue = gross revenue minus the price of returned sales (sales with a row in returns).
- Affiliate payouts are paid on every sale, including returned ones. Cost = sum(sales.affiliate_payout).
- Margin = net revenue - cost. Margin % = margin / net revenue * 100.
- Date sales, revenue and margin by sales.sold_at, and leads by leads.received_at.
- Acceptance rate (for a buyer) = accepted pings / all pings to that buyer.
- Sell-through rate = sold leads / non-duplicate leads received.
- Return rate = returned sales / sales, by the month of the sale.
- The data covers January 2025 to October 2026."""


def render() -> str:
    parts = []
    for table, info in TABLES.items():
        cols = "\n".join(f"  - {name}: {desc}" for name, desc in info["columns"].items())
        parts.append(f"Table {table}: {info['description']}\n{cols}")
    return "\n\n".join(parts) + "\n\n" + RULES
