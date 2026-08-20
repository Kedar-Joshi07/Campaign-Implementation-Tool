#!/usr/bin/env python3
"""
Generate two years of synthetic campaign-based sales history linked to CUSTOMER.

Main design
-----------
* Reads the customer master created by generate_us_customer_master.py.
* Uses customer_id as the ONLY row-level linkage to CUSTOMER.
* Has NO linkage to the independent 5M demographic/person universe.
* Default history: 2024-01-01 through 2025-12-31.
* Default size: exactly 570,000 campaign/customer observations.
* One row = one customer x one campaign observation.
* The same customer can appear in many campaigns, but at most once per campaign.
* Campaign response and purchase outcomes are deliberately correlated with
  customer attributes, product fit, channel, offer, seasonality and prior
  behavior so the future PU model has genuine synthetic signal to learn.
* pu_label = 1 only for a confirmed campaign-attributed purchase; 0 means
  UNLABELED, not a known negative.

Main output schema: 38 columns
------------------------------
campaign_sales_id, customer_id, campaign_id, product_id, order_id,
campaign_name, campaign_type, campaign_channel, campaign_start_date,
campaign_end_date, campaign_category, offer_type, offer_value, creative_id,
target_segment, product_name, product_category, product_subcategory,
product_price, product_cost, product_tier, product_launch_date, contact_date,
contacted_flag, delivery_status, engagement_flag, engagement_type,
response_flag, purchase_flag, purchase_date, quantity, gross_sales_amount,
discount_amount, net_sales_amount, gross_margin_amount, days_to_purchase,
campaign_attributed_sale_flag, pu_label

Auxiliary outputs
-----------------
* product_master.csv       - reference copy of the synthetic product catalog
* campaign_master.csv      - reference copy of campaigns
* campaign_sales_sample_10000.csv
* campaign_sales_summary.json

Dependencies
------------
pip install numpy pandas

Example
-------
python generate_campaign_sales.py \
  --customer-file ./output/customer_master_125000.csv.gz \
  --n-rows 570000 \
  --outdir ./output
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
DATA_START = date(2024, 1, 1)
DATA_END = date(2025, 12, 31)
ATTRIBUTION_WINDOW_DAYS = 30

CAMPAIGN_TYPES = np.array([
    "Acquisition", "Cross-sell", "Upsell", "Retention",
    "Win-back", "Loyalty", "Awareness"
], dtype=object)
CAMPAIGN_TYPE_P = np.array([.30, .20, .15, .15, .10, .05, .05])

CHANNELS = np.array([
    "Email", "Direct Mail", "SMS", "Paid Search", "Display",
    "Paid Social", "Telemarketing", "Website / On-site", "Mobile Push"
], dtype=object)
CHANNEL_P = np.array([.30, .14, .10, .09, .07, .12, .05, .07, .06])

TARGET_SEGMENTS = np.array([
    "Broad Prospecting",
    "Young Professionals",
    "High Income Professionals",
    "Family Households",
    "Value Seekers",
    "Mature Customers",
    "Digitally Oriented",
    "Prior Buyers",
], dtype=object)
TARGET_SEGMENT_P = np.array([.20, .13, .12, .14, .12, .09, .10, .10])

OFFER_TYPES = np.array([
    "None", "Percent Discount", "Fixed Discount", "Bundle Offer",
    "Free Shipping", "Loyalty Reward"
], dtype=object)
OFFER_P = np.array([.16, .34, .14, .12, .14, .10])

DELIVERY_BASE = {
    "Email": .955,
    "Direct Mail": .935,
    "SMS": .965,
    "Paid Search": .980,
    "Display": .975,
    "Paid Social": .975,
    "Telemarketing": .900,
    "Website / On-site": .990,
    "Mobile Push": .965,
}

ENGAGEMENT_BASE = {
    "Email": .235,
    "Direct Mail": .060,
    "SMS": .175,
    "Paid Search": .220,
    "Display": .065,
    "Paid Social": .125,
    "Telemarketing": .185,
    "Website / On-site": .255,
    "Mobile Push": .180,
}

RESPONSE_GIVEN_ENGAGEMENT = {
    "Email": .31,
    "Direct Mail": .40,
    "SMS": .36,
    "Paid Search": .42,
    "Display": .25,
    "Paid Social": .34,
    "Telemarketing": .52,
    "Website / On-site": .43,
    "Mobile Push": .33,
}

CAMPAIGN_SALES_HEADERS = [
    "campaign_sales_id", "customer_id", "campaign_id", "product_id", "order_id",
    "campaign_name", "campaign_type", "campaign_channel", "campaign_start_date",
    "campaign_end_date", "campaign_category", "offer_type", "offer_value",
    "creative_id", "target_segment", "product_name", "product_category",
    "product_subcategory", "product_price", "product_cost", "product_tier",
    "product_launch_date", "contact_date", "contacted_flag", "delivery_status",
    "engagement_flag", "engagement_type", "response_flag", "purchase_flag",
    "purchase_date", "quantity", "gross_sales_amount", "discount_amount",
    "net_sales_amount", "gross_margin_amount", "days_to_purchase",
    "campaign_attributed_sale_flag", "pu_label",
]

REQUIRED_CUSTOMER_COLUMNS = {
    "customer_id", "gender", "date_of_birth", "state",
    "individual_yearly_income", "family_member_count", "resident_status",
    "resident_type", "education", "employment_status",
    "type_of_employment", "marital_status",
}

EDUCATION_SCORE = {
    "Less than high school": 0.0,
    "High school diploma/GED": .20,
    "Some college - no degree": .35,
    "Associate degree": .48,
    "Bachelor degree": .70,
    "Master degree": .86,
    "Professional/Doctoral degree": 1.00,
}

EMPLOYED_STATUSES = {"Employed full-time", "Employed part-time"}


@dataclass
class Product:
    product_id: str
    product_name: str
    product_category: str
    product_subcategory: str
    product_price: float
    product_cost: float
    product_tier: str
    product_launch_date: str


@dataclass
class Campaign:
    campaign_id: str
    campaign_name: str
    campaign_type: str
    campaign_channel: str
    campaign_start_date: str
    campaign_end_date: str
    campaign_category: str
    offer_type: str
    offer_value: float
    creative_id: str
    target_segment: str
    product_id: str
    target_row_count: int


# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------
def sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20, 20)))


def normalize_weights(w: np.ndarray) -> np.ndarray:
    w = np.asarray(w, dtype=float)
    w = np.where(np.isfinite(w), w, 0.0)
    w = np.maximum(w, 1e-8)
    return w / w.sum()


def to_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def product_catalog(rng: np.random.Generator) -> list[Product]:
    # 8 categories x 6 products = 48 products.
    catalog = {
        "Electronics": [
            ("Wireless Earbuds", "Audio"), ("Portable Speaker", "Audio"),
            ("Tablet", "Computing"), ("Laptop", "Computing"),
            ("Smart Watch", "Wearables"), ("Portable SSD", "Storage"),
        ],
        "Home & Kitchen": [
            ("Air Fryer", "Kitchen Appliances"), ("Coffee Maker", "Kitchen Appliances"),
            ("Vacuum Cleaner", "Home Appliances"), ("Cookware Set", "Cookware"),
            ("Water Purifier", "Home Appliances"), ("Stand Mixer", "Kitchen Appliances"),
        ],
        "Fitness & Wellness": [
            ("Fitness Band", "Wearables"), ("Yoga Kit", "Fitness Accessories"),
            ("Adjustable Dumbbell Set", "Strength Training"), ("Massage Device", "Recovery"),
            ("Exercise Bike", "Cardio Equipment"), ("Nutrition Blender", "Wellness Appliances"),
        ],
        "Personal Care": [
            ("Electric Grooming Kit", "Grooming"), ("Skin Care Set", "Skin Care"),
            ("Hair Styling Tool", "Hair Care"), ("Electric Toothbrush", "Oral Care"),
            ("Personal Care Bundle", "Personal Care"), ("Travel Grooming Kit", "Grooming"),
        ],
        "Apparel & Accessories": [
            ("Everyday Jacket", "Outerwear"), ("Performance Shoes", "Footwear"),
            ("Travel Backpack", "Bags"), ("Casual Watch", "Accessories"),
            ("Premium Wallet", "Accessories"), ("Athleisure Set", "Activewear"),
        ],
        "Outdoor & Recreation": [
            ("Camping Tent", "Camping"), ("Hiking Pack", "Hiking"),
            ("Portable Grill", "Outdoor Cooking"), ("Cycling Gear Set", "Cycling"),
            ("Cooler", "Outdoor Accessories"), ("Inflatable Paddle Board", "Water Recreation"),
        ],
        "Office & Productivity": [
            ("Ergonomic Chair", "Office Furniture"), ("Mechanical Keyboard", "Computer Accessories"),
            ("Monitor", "Displays"), ("Webcam", "Computer Accessories"),
            ("Desk Lamp", "Office Accessories"), ("Document Scanner", "Office Electronics"),
        ],
        "Smart Home": [
            ("Smart Speaker", "Smart Assistants"), ("Smart Bulb Kit", "Smart Lighting"),
            ("Video Doorbell", "Home Security"), ("Smart Thermostat", "Climate Control"),
            ("Indoor Camera", "Home Security"), ("Smart Plug Pack", "Smart Lighting"),
        ],
    }

    # Broad retail price bands by category.
    price_ranges = {
        "Electronics": (45, 1100),
        "Home & Kitchen": (35, 700),
        "Fitness & Wellness": (25, 850),
        "Personal Care": (20, 320),
        "Apparel & Accessories": (25, 280),
        "Outdoor & Recreation": (35, 950),
        "Office & Productivity": (25, 900),
        "Smart Home": (25, 450),
    }

    products: list[Product] = []
    pid = 1
    # First 28 launch before 2024; remaining launches are spread across 2024-2025.
    launch_dates: list[date] = []
    for i in range(48):
        if i < 28:
            start, end = date(2022, 1, 1), date(2023, 12, 15)
        elif i < 38:
            start, end = date(2024, 1, 10), date(2024, 11, 15)
        else:
            start, end = date(2025, 1, 10), date(2025, 9, 30)
        span = (end - start).days
        launch_dates.append(start + timedelta(days=int(rng.integers(0, span + 1))))
    launch_dates.sort()

    for category, items in catalog.items():
        low, high = price_ranges[category]
        # Six tiered prices per category, with natural jitter.
        base_prices = np.geomspace(low, high, 6)
        for j, (name, subcat) in enumerate(items):
            price = float(np.round(base_prices[j] * rng.uniform(.90, 1.10), 2))
            tier = "Economy" if j < 2 else ("Standard" if j < 4 else "Premium")
            cost_ratio = rng.uniform(.42, .64) if tier != "Premium" else rng.uniform(.38, .58)
            cost = float(np.round(price * cost_ratio, 2))
            products.append(Product(
                product_id=f"PRD{pid:03d}",
                product_name=f"{name} {pid:02d}",
                product_category=category,
                product_subcategory=subcat,
                product_price=price,
                product_cost=cost,
                product_tier=tier,
                product_launch_date=launch_dates[pid - 1].isoformat(),
            ))
            pid += 1
    return products


def offer_value_for(rng: np.random.Generator, offer_type: str, price: float) -> float:
    if offer_type == "Percent Discount":
        return float(rng.choice([5, 10, 15, 20, 25], p=[.08, .28, .32, .23, .09]))
    if offer_type == "Fixed Discount":
        candidates = np.array([10, 15, 20, 25, 30, 40, 50, 75], dtype=float)
        candidates = candidates[candidates < max(price * .45, 12)]
        return float(rng.choice(candidates if len(candidates) else np.array([10.0])))
    if offer_type == "Bundle Offer":
        return float(rng.choice([5, 8, 10, 12, 15]))  # implicit percent-equivalent
    if offer_type == "Loyalty Reward":
        return float(rng.choice([5, 10, 15, 20]))      # implicit percent-equivalent
    return 0.0


def campaign_category_for(campaign_type: str, month: int) -> str:
    if month in {11, 12}:
        return "Holiday / Year-end Promotion"
    if month in {5, 6, 7}:
        return "Summer Promotion"
    return {
        "Acquisition": "Customer Acquisition",
        "Cross-sell": "Cross-sell Promotion",
        "Upsell": "Premium / Upgrade Promotion",
        "Retention": "Retention Offer",
        "Win-back": "Reactivation Offer",
        "Loyalty": "Loyalty Promotion",
        "Awareness": "Product Awareness",
    }[campaign_type]


def build_campaigns(
    rng: np.random.Generator,
    products: list[Product],
    n_campaigns: int,
    n_rows: int,
) -> list[Campaign]:
    # Allocate the exact requested row count across campaigns while keeping
    # materially different campaign sizes.
    min_each = min(1500, max(1, n_rows // max(n_campaigns * 4, 1)))
    guaranteed = min_each * n_campaigns
    if guaranteed > n_rows:
        raise ValueError("n_rows is too small for n_campaigns")
    remaining = n_rows - guaranteed
    size_w = normalize_weights(rng.gamma(shape=2.2, scale=1.0, size=n_campaigns))
    extra = rng.multinomial(remaining, size_w)
    sizes = extra + min_each

    total_days = (DATA_END - DATA_START).days
    base_offsets = np.linspace(2, total_days - 8, n_campaigns)
    jitter = rng.integers(-3, 4, size=n_campaigns)
    start_dates = [DATA_START + timedelta(days=int(max(0, min(total_days, o + j)))) for o, j in zip(base_offsets, jitter)]
    start_dates.sort()

    campaigns: list[Campaign] = []
    for i, (start, target_rows) in enumerate(zip(start_dates, sizes), start=1):
        duration = int(rng.integers(8, 29))
        end = min(DATA_END, start + timedelta(days=duration))
        campaign_type = str(rng.choice(CAMPAIGN_TYPES, p=CAMPAIGN_TYPE_P))
        channel = str(rng.choice(CHANNELS, p=CHANNEL_P))
        target_segment = str(rng.choice(TARGET_SEGMENTS, p=TARGET_SEGMENT_P))

        available = [p for p in products if to_date(p.product_launch_date) <= start]
        product = available[int(rng.integers(0, len(available)))]

        # Awareness campaigns more often carry no offer; retention/loyalty more often do.
        local_offer_p = OFFER_P.copy()
        if campaign_type == "Awareness":
            local_offer_p *= np.array([2.7, .7, .5, .6, .8, .4])
        elif campaign_type in {"Retention", "Win-back", "Loyalty"}:
            local_offer_p *= np.array([.5, 1.25, 1.15, 1.15, .9, 1.65])
        local_offer_p = normalize_weights(local_offer_p)
        offer_type = str(rng.choice(OFFER_TYPES, p=local_offer_p))
        offer_value = offer_value_for(rng, offer_type, product.product_price)

        campaign_category = campaign_category_for(campaign_type, start.month)
        campaign_id = f"CMP{i:04d}"
        campaign_name = f"{start.year} {campaign_category} {product.product_category} {i:03d}"
        campaigns.append(Campaign(
            campaign_id=campaign_id,
            campaign_name=campaign_name,
            campaign_type=campaign_type,
            campaign_channel=channel,
            campaign_start_date=start.isoformat(),
            campaign_end_date=end.isoformat(),
            campaign_category=campaign_category,
            offer_type=offer_type,
            offer_value=offer_value,
            creative_id=f"CRT{i:04d}-{channel.replace(' ', '').replace('/', '')[:5].upper()}",
            target_segment=target_segment,
            product_id=product.product_id,
            target_row_count=int(target_rows),
        ))
    return campaigns


def customer_age_on(dob: pd.Series, campaign_date: date) -> np.ndarray:
    # Approximate fractional age is sufficient for targeting and latent behavior.
    ref = pd.Timestamp(campaign_date)
    return ((ref - dob).dt.days.to_numpy(dtype=float) / 365.2425)


def target_segment_weight(
    segment: str,
    age: np.ndarray,
    income: np.ndarray,
    family: np.ndarray,
    education_score: np.ndarray,
    employed: np.ndarray,
    resident_type: np.ndarray,
) -> np.ndarray:
    w = np.ones(len(age), dtype=float)
    if segment == "Young Professionals":
        w *= 0.35 + 2.3 * ((age >= 22) & (age <= 38)) + .75 * employed
    elif segment == "High Income Professionals":
        w *= 0.30 + 2.2 * (income >= 100000) + .85 * education_score + .65 * employed
    elif segment == "Family Households":
        w *= 0.35 + 1.9 * (family >= 3) + .65 * ((age >= 28) & (age <= 58))
    elif segment == "Value Seekers":
        w *= 0.45 + 1.35 * ((income >= 25000) & (income <= 85000)) + .45 * (family >= 2)
    elif segment == "Mature Customers":
        w *= 0.35 + 2.25 * (age >= 55)
    elif segment == "Digitally Oriented":
        w *= 0.45 + 1.70 * (age <= 44) + .45 * education_score
    elif segment == "Prior Buyers":
        # Prior-purchase weighting is added separately from dynamic history.
        w *= .75 + .35 * employed
    return np.maximum(w, .05)


def product_affinity(
    category: str,
    age: np.ndarray,
    income: np.ndarray,
    family: np.ndarray,
    education_score: np.ndarray,
    employed: np.ndarray,
    resident_type: np.ndarray,
    latent: np.ndarray,
) -> np.ndarray:
    income_z = np.clip((np.log1p(income) - math.log(60000)) / 1.2, -2.0, 2.0)
    age_mid = ((age >= 27) & (age <= 58)).astype(float)
    younger = (age <= 40).astype(float)
    suburban = np.isin(resident_type, ["Inner suburban", "Outer suburban/peri-urban"]).astype(float)

    score = -.15 + .25 * latent
    if category == "Electronics":
        score += .45 * younger + .35 * income_z + .35 * education_score
    elif category == "Home & Kitchen":
        score += .55 * (family >= 2) + .45 * age_mid + .20 * suburban
    elif category == "Fitness & Wellness":
        score += .48 * (age <= 50) + .28 * employed + .18 * income_z
    elif category == "Personal Care":
        score += .32 * ((age >= 22) & (age <= 60)) + .15 * income_z
    elif category == "Apparel & Accessories":
        score += .42 * younger + .20 * employed + .12 * income_z
    elif category == "Outdoor & Recreation":
        score += .42 * age_mid + .28 * suburban + .20 * income_z
    elif category == "Office & Productivity":
        score += .50 * employed + .42 * education_score + .20 * income_z
    elif category == "Smart Home":
        score += .40 * income_z + .35 * (family >= 2) + .28 * suburban + .18 * education_score
    return np.asarray(sigmoid(score), dtype=float)


def channel_fit(channel: str, age: np.ndarray) -> np.ndarray:
    fit = np.ones(len(age), dtype=float)
    if channel in {"Paid Social", "Mobile Push", "SMS"}:
        fit *= np.where(age <= 40, 1.25, np.where(age <= 60, 1.0, .78))
    elif channel == "Direct Mail":
        fit *= np.where(age >= 50, 1.25, np.where(age >= 35, 1.05, .78))
    elif channel == "Telemarketing":
        fit *= np.where(age >= 45, 1.12, .88)
    elif channel in {"Paid Search", "Website / On-site"}:
        fit *= np.where(age <= 55, 1.12, .90)
    return fit


def offer_strength(offer_type: str, offer_value: float) -> float:
    if offer_type == "Percent Discount":
        return min(.65, offer_value / 35)
    if offer_type == "Fixed Discount":
        return min(.55, offer_value / 100)
    if offer_type == "Bundle Offer":
        return .30
    if offer_type == "Free Shipping":
        return .18
    if offer_type == "Loyalty Reward":
        return .32
    return 0.0


def engagement_type_for(rng: np.random.Generator, channel: str) -> str:
    choices = {
        "Email": (["Open", "Click"], [.68, .32]),
        "Direct Mail": (["QR Scan", "Website Visit", "Call"], [.32, .45, .23]),
        "SMS": (["Link Click", "Reply"], [.78, .22]),
        "Paid Search": (["Click", "Website Visit"], [.58, .42]),
        "Display": (["Click", "Website Visit"], [.72, .28]),
        "Paid Social": (["Click", "Website Visit"], [.68, .32]),
        "Telemarketing": (["Call Connected", "Callback"], [.78, .22]),
        "Website / On-site": (["Page Visit", "Form Submit"], [.82, .18]),
        "Mobile Push": (["Open", "Click"], [.64, .36]),
    }
    vals, probs = choices[channel]
    return str(rng.choice(vals, p=probs))


def discount_amount(offer_type: str, offer_value: float, gross: float) -> float:
    if offer_type == "Percent Discount":
        return round(gross * offer_value / 100.0, 2)
    if offer_type == "Fixed Discount":
        return round(min(gross * .45, offer_value), 2)
    if offer_type == "Bundle Offer":
        return round(gross * offer_value / 100.0, 2)
    if offer_type == "Loyalty Reward":
        return round(gross * offer_value / 100.0, 2)
    return 0.0


# -----------------------------------------------------------------------------
# Generator
# -----------------------------------------------------------------------------
def generate(args: argparse.Namespace) -> None:
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out_file = outdir / args.output
    sample_file = outdir / args.sample_output
    summary_file = outdir / args.summary_output
    campaign_master_file = outdir / args.campaign_master_output
    product_master_file = outdir / args.product_master_output

    rng = np.random.default_rng(args.seed)

    print(f"Reading customer master: {args.customer_file}")
    customers = pd.read_csv(args.customer_file, compression="infer", low_memory=False)
    missing = REQUIRED_CUSTOMER_COLUMNS.difference(customers.columns)
    if missing:
        raise ValueError(f"Customer file is missing required columns: {sorted(missing)}")
    if customers["customer_id"].duplicated().any():
        raise ValueError("customer_id must be unique in the customer master")
    if args.n_rows <= 0:
        raise ValueError("n_rows must be positive")

    n_customers = len(customers)
    if n_customers < 1000:
        print("WARNING: very small customer master; default calibration assumes a much larger population")

    customers["date_of_birth"] = pd.to_datetime(customers["date_of_birth"], errors="raise")
    income = pd.to_numeric(customers["individual_yearly_income"], errors="raise").to_numpy(dtype=float)
    family = pd.to_numeric(customers["family_member_count"], errors="raise").to_numpy(dtype=float)
    education_score = customers["education"].map(EDUCATION_SCORE).fillna(.30).to_numpy(dtype=float)
    employed = customers["employment_status"].isin(EMPLOYED_STATUSES).to_numpy(dtype=float)
    resident_type = customers["resident_type"].astype(str).to_numpy(dtype=object)
    customer_ids = customers["customer_id"].astype(str).to_numpy(dtype=object)

    # Stable latent customer preference captures unobserved taste/brand affinity.
    latent = rng.normal(0, 1, size=n_customers)

    # Dynamic historical state. These are used ONLY to synthesize coherent
    # behavior and are not written as raw features, preventing leakage by design.
    prior_exposure = np.zeros(n_customers, dtype=np.int32)
    prior_response = np.zeros(n_customers, dtype=np.int32)
    prior_purchase = np.zeros(n_customers, dtype=np.int32)
    lifetime_spend = np.zeros(n_customers, dtype=float)
    last_contact_ordinal = np.full(n_customers, -1, dtype=np.int32)
    last_purchase_ordinal = np.full(n_customers, -1, dtype=np.int32)

    products = product_catalog(rng)
    product_by_id = {p.product_id: p for p in products}
    campaigns = build_campaigns(rng, products, args.n_campaigns, args.n_rows)

    if max(c.target_row_count for c in campaigns) > n_customers:
        raise ValueError(
            "At least one campaign target size exceeds the number of customers. "
            "Increase customer count or campaign count."
        )

    # Write auxiliary reference masters.
    with open(product_master_file, "w", encoding="utf-8", newline="") as pf:
        fields = list(asdict(products[0]).keys())
        w = csv.DictWriter(pf, fieldnames=fields)
        w.writeheader()
        for p in products:
            w.writerow(asdict(p))

    with open(campaign_master_file, "w", encoding="utf-8", newline="") as cf:
        fields = list(asdict(campaigns[0]).keys())
        w = csv.DictWriter(cf, fieldnames=fields)
        w.writeheader()
        for c in campaigns:
            w.writerow(asdict(c))

    sample_rows: list[list[object]] = []
    counters = Counter()
    channel_counter = Counter()
    type_counter = Counter()
    product_category_counter = Counter()
    total_net_sales = 0.0
    total_gross_margin = 0.0
    order_sequence = 0
    row_sequence = 0

    opener = gzip.open if str(out_file).endswith(".gz") else open
    with opener(out_file, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CAMPAIGN_SALES_HEADERS)

        for ci, campaign in enumerate(campaigns, start=1):
            start = to_date(campaign.campaign_start_date)
            end = to_date(campaign.campaign_end_date)
            product = product_by_id[campaign.product_id]
            age = customer_age_on(customers["date_of_birth"], start)

            affinity = product_affinity(
                product.product_category, age, income, family, education_score,
                employed, resident_type, latent,
            )
            segment_w = target_segment_weight(
                campaign.target_segment, age, income, family, education_score,
                employed, resident_type,
            )

            # Dynamic business targeting based only on information known before
            # the current campaign.
            type_w = np.ones(n_customers, dtype=float)
            if campaign.campaign_type == "Acquisition":
                type_w *= np.where(prior_purchase == 0, 1.50, .58)
            elif campaign.campaign_type in {"Cross-sell", "Upsell", "Retention", "Loyalty"}:
                type_w *= np.where(prior_purchase > 0, 1.75, .52)
            elif campaign.campaign_type == "Win-back":
                days_since_purchase = np.where(
                    last_purchase_ordinal >= 0,
                    start.toordinal() - last_purchase_ordinal,
                    9999,
                )
                type_w *= np.where((prior_purchase > 0) & (days_since_purchase >= 120), 2.35, .42)

            if campaign.target_segment == "Prior Buyers":
                type_w *= np.where(prior_purchase > 0, 2.2, .45)

            # Campaign fatigue prevents hyper-active customers from dominating.
            fatigue = np.exp(-.025 * np.maximum(prior_exposure - 5, 0))
            selection_w = normalize_weights(
                segment_w * type_w * fatigue * (.55 + 1.15 * affinity) * np.exp(.12 * latent)
            )

            selected = rng.choice(
                n_customers,
                size=campaign.target_row_count,
                replace=False,
                p=selection_w,
            )

            # Contact dates are within campaign window.
            campaign_days = max(0, (end - start).days)
            contact_offsets = rng.integers(0, campaign_days + 1, size=len(selected))
            contact_dates = np.array([start + timedelta(days=int(x)) for x in contact_offsets], dtype=object)

            # Contact + delivery.
            contacted = rng.random(len(selected)) < .988
            delivered = contacted & (rng.random(len(selected)) < DELIVERY_BASE[campaign.campaign_channel])

            delivery_status = np.full(len(selected), "Not Contacted", dtype=object)
            delivery_status[contacted & delivered] = "Delivered"
            failed = contacted & ~delivered
            if campaign.campaign_channel == "Email":
                delivery_status[failed] = np.where(rng.random(failed.sum()) < .70, "Bounced", "Failed")
            elif campaign.campaign_channel == "Direct Mail":
                delivery_status[failed] = np.where(rng.random(failed.sum()) < .72, "Returned", "Failed")
            else:
                delivery_status[failed] = "Failed"

            sel_affinity = affinity[selected]
            sel_age = age[selected]
            sel_income = income[selected]
            sel_latent = latent[selected]
            sel_prior_resp = prior_response[selected]
            sel_prior_purch = prior_purchase[selected]
            sel_prior_exp = prior_exposure[selected]
            sel_last_contact = last_contact_ordinal[selected]

            days_since_contact = np.where(
                sel_last_contact >= 0,
                np.array([d.toordinal() for d in contact_dates]) - sel_last_contact,
                9999,
            )
            recent_fatigue = np.where(days_since_contact < 14, .72, np.where(days_since_contact < 30, .88, 1.0))

            off_strength = offer_strength(campaign.offer_type, campaign.offer_value)
            cfit = channel_fit(campaign.campaign_channel, sel_age)
            engage_p = ENGAGEMENT_BASE[campaign.campaign_channel] * (
                .62 + .92 * sel_affinity
            ) * cfit * (1 + .38 * off_strength) * (
                1 + .08 * np.minimum(sel_prior_resp, 4)
            ) * recent_fatigue
            engage_p = np.clip(engage_p, .003, .72)
            engaged = delivered & (rng.random(len(selected)) < engage_p)

            response_p = RESPONSE_GIVEN_ENGAGEMENT[campaign.campaign_channel] * (
                .70 + .72 * sel_affinity
            ) * (1 + .45 * off_strength)
            response_p = np.clip(response_p, .02, .88)
            response = engaged & (rng.random(len(selected)) < response_p)

            # Purchase propensity. This is deliberately synthetic and nonlinear,
            # creating learnable relationships without defining true negatives.
            monthly_income = np.maximum(sel_income / 12.0, 900.0)
            affordability_ratio = product.product_price / monthly_income
            affordability_penalty = np.clip(np.log1p(affordability_ratio * 5), 0, 2.2)
            seasonal_boost = .18 if start.month in {11, 12} else (.07 if start.month in {5, 6, 7} else 0.0)
            channel_purchase_boost = .18 if campaign.campaign_channel in {"Paid Search", "Website / On-site"} else 0.0
            repeat_boost = np.minimum(sel_prior_purch, 4) * .12
            type_boost = .16 if campaign.campaign_type in {"Retention", "Cross-sell", "Upsell", "Loyalty"} else 0.0

            purchase_logit = (
                -3.10
                + 1.05 * engaged.astype(float)
                + .78 * response.astype(float)
                + .95 * (sel_affinity - .50)
                + .42 * off_strength
                + repeat_boost
                + type_boost
                + seasonal_boost
                + channel_purchase_boost
                + .20 * sel_latent
                - .42 * affordability_penalty
                - .025 * np.maximum(sel_prior_exp - 10, 0)
            )
            purchase_p = np.asarray(sigmoid(purchase_logit), dtype=float)
            purchase = delivered & (rng.random(len(selected)) < purchase_p)

            # Build rows. Purchases can occur up to 45 days later; attribution is
            # separately determined using the 30-day window.
            for local_i, customer_idx in enumerate(selected):
                row_sequence += 1
                campaign_sales_id = f"CS{row_sequence:09d}"
                customer_id = customer_ids[customer_idx]
                contact_date = contact_dates[local_i]

                engagement_flag = int(engaged[local_i])
                response_flag = int(response[local_i])
                engagement_type = engagement_type_for(rng, campaign.campaign_channel) if engagement_flag else ""

                purchase_flag = int(purchase[local_i])
                order_id = ""
                purchase_date = ""
                quantity = 0
                gross_sales = 0.0
                discount = 0.0
                net_sales = 0.0
                gross_margin = 0.0
                days_to_purchase: int | str = ""
                attributed = 0

                if purchase_flag:
                    # Engaged customers tend to convert sooner.
                    if engagement_flag:
                        days = int(min(45, max(0, round(rng.exponential(8.0)))))
                    else:
                        days = int(rng.integers(5, 46))

                    max_days = (DATA_END - contact_date).days
                    if max_days < 0:
                        purchase_flag = 0
                    else:
                        days = min(days, max_days)
                        pdate = contact_date + timedelta(days=days)
                        days_to_purchase = days
                        purchase_date = pdate.isoformat()
                        quantity = int(rng.choice([1, 2, 3, 4], p=[.86, .10, .03, .01]))
                        gross_sales = round(product.product_price * quantity, 2)
                        discount = discount_amount(campaign.offer_type, campaign.offer_value, gross_sales)
                        net_sales = round(max(0.0, gross_sales - discount), 2)
                        gross_margin = round(net_sales - product.product_cost * quantity, 2)
                        order_sequence += 1
                        order_id = f"ORD{order_sequence:09d}"

                        # Attribution is intentionally stricter than purchase.
                        if days <= ATTRIBUTION_WINDOW_DAYS:
                            if response_flag:
                                attr_p = .95
                            elif engagement_flag:
                                attr_p = .84
                            else:
                                attr_p = .48
                            attributed = int(rng.random() < attr_p)
                        if attributed:
                            response_flag = 1

                pu_label = attributed  # 0 = unlabeled, not negative.

                row = [
                    campaign_sales_id,
                    customer_id,
                    campaign.campaign_id,
                    product.product_id,
                    order_id,
                    campaign.campaign_name,
                    campaign.campaign_type,
                    campaign.campaign_channel,
                    campaign.campaign_start_date,
                    campaign.campaign_end_date,
                    campaign.campaign_category,
                    campaign.offer_type,
                    round(campaign.offer_value, 2),
                    campaign.creative_id,
                    campaign.target_segment,
                    product.product_name,
                    product.product_category,
                    product.product_subcategory,
                    round(product.product_price, 2),
                    round(product.product_cost, 2),
                    product.product_tier,
                    product.product_launch_date,
                    contact_date.isoformat(),
                    int(contacted[local_i]),
                    delivery_status[local_i],
                    engagement_flag,
                    engagement_type,
                    response_flag,
                    purchase_flag,
                    purchase_date,
                    quantity,
                    gross_sales,
                    discount,
                    net_sales,
                    gross_margin,
                    days_to_purchase,
                    attributed,
                    pu_label,
                ]
                writer.writerow(row)

                if len(sample_rows) < args.sample_rows:
                    sample_rows.append(row)

                # Update dynamic history only after this observation.
                prior_exposure[customer_idx] += int(contacted[local_i])
                if response_flag:
                    prior_response[customer_idx] += 1
                last_contact_ordinal[customer_idx] = contact_date.toordinal()
                if purchase_flag:
                    prior_purchase[customer_idx] += 1
                    lifetime_spend[customer_idx] += net_sales
                    if purchase_date:
                        last_purchase_ordinal[customer_idx] = to_date(purchase_date).toordinal()

                counters["contacted"] += int(contacted[local_i])
                counters["delivered"] += int(delivered[local_i])
                counters["engaged"] += engagement_flag
                counters["response"] += response_flag
                counters["purchase"] += purchase_flag
                counters["attributed"] += attributed
                channel_counter[campaign.campaign_channel] += 1
                type_counter[campaign.campaign_type] += 1
                product_category_counter[product.product_category] += 1
                total_net_sales += net_sales
                total_gross_margin += gross_margin

            print(
                f"Campaign {ci:02d}/{len(campaigns)} | {campaign.campaign_id} | "
                f"rows={campaign.target_row_count:,} | cumulative={row_sequence:,}"
            )

    if row_sequence != args.n_rows:
        raise RuntimeError(f"Expected {args.n_rows:,} rows but wrote {row_sequence:,}")

    with open(sample_file, "w", encoding="utf-8", newline="") as sf:
        sw = csv.writer(sf)
        sw.writerow(CAMPAIGN_SALES_HEADERS)
        sw.writerows(sample_rows)

    positives = counters["attributed"]
    summary = {
        "rows": row_sequence,
        "columns": len(CAMPAIGN_SALES_HEADERS),
        "customer_rows_loaded": n_customers,
        "distinct_campaigns": len(campaigns),
        "distinct_products": len(products),
        "data_start": DATA_START.isoformat(),
        "data_end": DATA_END.isoformat(),
        "attribution_window_days": ATTRIBUTION_WINDOW_DAYS,
        "seed": args.seed,
        "contacted_rows": counters["contacted"],
        "delivered_rows": counters["delivered"],
        "engaged_rows": counters["engaged"],
        "response_rows": counters["response"],
        "purchase_rows": counters["purchase"],
        "campaign_attributed_sales": positives,
        "pu_positive_rate": round(positives / row_sequence, 6),
        "pu_unlabeled_rows": row_sequence - positives,
        "total_net_sales": round(total_net_sales, 2),
        "total_gross_margin": round(total_gross_margin, 2),
        "campaign_type_distribution": dict(type_counter),
        "channel_distribution": dict(channel_counter),
        "product_category_distribution": dict(product_category_counter),
        "label_semantics": "pu_label=1 is a confirmed campaign-attributed purchase. pu_label=0 is unlabeled and must NOT be treated as a confirmed negative.",
        "anti_leakage": "Prior behavior is used internally in chronological order to synthesize realistic outcomes but is not stored as precomputed raw features. Future feature engineering should rebuild prior features using only events before each observation date.",
        "main_output": str(out_file),
        "campaign_master": str(campaign_master_file),
        "product_master": str(product_master_file),
        "sample_output": str(sample_file),
    }
    with open(summary_file, "w", encoding="utf-8") as jf:
        json.dump(summary, jf, indent=2)

    print(
        "\nDONE\n"
        f"Campaign sales: {out_file}\n"
        f"Campaign master: {campaign_master_file}\n"
        f"Product master: {product_master_file}\n"
        f"Sample: {sample_file}\n"
        f"Summary: {summary_file}\n"
        f"PU positives: {positives:,} ({positives / row_sequence:.2%})"
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate synthetic two-year campaign sales data")
    p.add_argument("--customer-file", default="./output/customer_master_125000.csv.gz")
    p.add_argument("--n-rows", type=int, default=570_000)
    p.add_argument("--n-campaigns", type=int, default=96)
    p.add_argument("--seed", type=int, default=20260820)
    p.add_argument("--outdir", default="./output")
    p.add_argument("--output", default="campaign_sales_570000.csv.gz")
    p.add_argument("--sample-output", default="campaign_sales_sample_10000.csv")
    p.add_argument("--summary-output", default="campaign_sales_summary.json")
    p.add_argument("--campaign-master-output", default="campaign_master.csv")
    p.add_argument("--product-master-output", default="product_master.csv")
    p.add_argument("--sample-rows", type=int, default=10_000)
    return p.parse_args()


if __name__ == "__main__":
    generate(parse_args())
