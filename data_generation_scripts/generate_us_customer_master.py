#!/usr/bin/env python3
"""
Generate a synthetic U.S.-focused CUSTOMER master for the PU-learning campaign project.

Design goals
------------
* Independent from the 5M demographic universe: no person_id reuse and no rows copied.
* Compatible feature vocabulary with the previously generated demographic dataset.
* Default size: 125,000 adult customers.
* Geography: same 27 high-urban-population U.S. states used by the demographic universe.
* Safe dummy contacts: IANA example.* email domains and fictional 555-0100..0199 phones.
* Reproducible through --seed.

Output schema (22 columns)
--------------------------
customer_id, first_name, last_name, gender, date_of_birth,
address_line_1, address_line_2, street, postal_code, city, state, country,
phone_number, email, individual_yearly_income, family_member_count,
resident_status, resident_type, education, employment_status,
type_of_employment, marital_status

Dependencies
------------
pip install numpy faker

Example
-------
python generate_us_customer_master.py --n-customers 125000 --outdir ./output
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import random
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
from faker import Faker


# -----------------------------------------------------------------------------
# Geography and calibration anchors
# -----------------------------------------------------------------------------
# 2020 urban-population counts for the same 27 states used in the demographic
# universe. They are used only as sampling weights, not as row-level source data.
URBAN = {
    "CA": ("California", 37259490, 94.2366),
    "TX": ("Texas", 24400697, 83.7203),
    "FL": ("Florida", 19714806, 91.5342),
    "NY": ("New York", 17665166, 87.4459),
    "IL": ("Illinois", 11137590, 86.9275),
    "PA": ("Pennsylvania", 9941070, 76.4539),
    "OH": ("Ohio", 9001099, 76.2841),
    "NJ": ("New Jersey", 8708779, 93.7537),
    "GA": ("Georgia", 7933986, 74.0670),
    "MI": ("Michigan", 7404258, 73.4744),
    "NC": ("North Carolina", 6964727, 66.7159),
    "VA": ("Virginia", 6528313, 75.6345),
    "WA": ("Washington", 6424035, 83.3718),
    "MA": ("Massachusetts", 6416895, 91.2798),
    "AZ": ("Arizona", 6385230, 89.2852),
    "MD": ("Maryland", 5288760, 85.6171),
    "CO": ("Colorado", 4966936, 86.0267),
    "IN": ("Indiana", 4829686, 71.1763),
    "TN": ("Tennessee", 4577282, 66.2334),
    "MO": ("Missouri", 4275663, 69.4675),
    "MN": ("Minnesota", 4101754, 71.8787),
    "WI": ("Wisconsin", 3953691, 67.0831),
    "SC": ("South Carolina", 3477869, 67.9480),
    "OR": ("Oregon", 3410984, 80.4998),
    "LA": ("Louisiana", 3332237, 71.5417),
    "CT": ("Connecticut", 3110153, 86.2507),
    "UT": ("Utah", 2937303, 89.7814),
}

# Median-household-income-style anchor, female share, bachelors+ target,
# foreign-born target. These are broad synthetic calibration parameters.
STATE_CFG = {
    "CA": (100300, .502, .37, .27), "TX": (78000, .503, .32, .17),
    "FL": (74000, .510, .34, .21), "NY": (85000, .514, .40, .23),
    "IL": (83000, .509, .38, .14), "PA": (77000, .510, .35, .08),
    "OH": (71000, .509, .31, .05), "NJ": (103000, .511, .44, .23),
    "GA": (78000, .512, .34, .11), "MI": (72000, .507, .32, .07),
    "NC": (76000, .512, .36, .09), "VA": (90000, .506, .42, .13),
    "WA": (96000, .500, .40, .15), "MA": (104000, .512, .48, .17),
    "AZ": (77000, .504, .33, .13), "MD": (101000, .513, .43, .16),
    "CO": (93000, .498, .45, .10), "IN": (71000, .507, .29, .06),
    "TN": (72000, .512, .31, .06), "MO": (73000, .509, .32, .05),
    "MN": (85000, .502, .40, .09), "WI": (76000, .504, .32, .06),
    "SC": (72000, .515, .32, .06), "OR": (83000, .506, .38, .10),
    "LA": (60000, .512, .27, .04), "CT": (93000, .512, .43, .15),
    "UT": (96000, .497, .38, .09),
}

CITIES = {
    "CA": [("Los Angeles", "900", ["213", "310"]), ("San Diego", "921", ["619", "858"]), ("San Jose", "951", ["408", "669"]), ("San Francisco", "941", ["415", "628"]), ("Sacramento", "958", ["916", "279"]), ("Fresno", "937", ["559"])],
    "TX": [("Houston", "770", ["713", "281"]), ("Dallas", "752", ["214", "469"]), ("Austin", "787", ["512", "737"]), ("San Antonio", "782", ["210"]), ("Fort Worth", "761", ["817", "682"]), ("El Paso", "799", ["915"])],
    "FL": [("Miami", "331", ["305", "786"]), ("Orlando", "328", ["407", "689"]), ("Tampa", "336", ["813"]), ("Jacksonville", "322", ["904"]), ("Fort Lauderdale", "333", ["954", "754"])],
    "NY": [("New York", "100", ["212", "646"]), ("Brooklyn", "112", ["718", "347"]), ("Buffalo", "142", ["716"]), ("Rochester", "146", ["585"]), ("Albany", "122", ["518"]), ("Syracuse", "132", ["315"])],
    "IL": [("Chicago", "606", ["312", "773"]), ("Aurora", "605", ["630"]), ("Rockford", "611", ["815"]), ("Springfield", "627", ["217"])],
    "PA": [("Philadelphia", "191", ["215", "267"]), ("Pittsburgh", "152", ["412", "878"]), ("Allentown", "181", ["610"]), ("Harrisburg", "171", ["717"]), ("Erie", "165", ["814"])],
    "OH": [("Columbus", "432", ["614"]), ("Cleveland", "441", ["216"]), ("Cincinnati", "452", ["513"]), ("Toledo", "436", ["419"]), ("Akron", "443", ["330"])],
    "NJ": [("Newark", "071", ["973"]), ("Jersey City", "073", ["201"]), ("Paterson", "075", ["973"]), ("Trenton", "086", ["609"]), ("Edison", "088", ["732"])],
    "GA": [("Atlanta", "303", ["404", "470"]), ("Savannah", "314", ["912"]), ("Augusta", "309", ["706"]), ("Columbus", "319", ["706"])],
    "MI": [("Detroit", "482", ["313"]), ("Grand Rapids", "495", ["616"]), ("Ann Arbor", "481", ["734"]), ("Lansing", "489", ["517"]), ("Flint", "485", ["810"])],
    "NC": [("Charlotte", "282", ["704", "980"]), ("Raleigh", "276", ["919", "984"]), ("Greensboro", "274", ["336"]), ("Durham", "277", ["919"]), ("Winston-Salem", "271", ["336"])],
    "VA": [("Virginia Beach", "234", ["757"]), ("Richmond", "232", ["804"]), ("Norfolk", "235", ["757"]), ("Alexandria", "223", ["703", "571"]), ("Arlington", "222", ["703", "571"])],
    "WA": [("Seattle", "981", ["206"]), ("Spokane", "992", ["509"]), ("Tacoma", "984", ["253"]), ("Bellevue", "980", ["425"]), ("Vancouver", "986", ["360"])],
    "MA": [("Boston", "021", ["617", "857"]), ("Worcester", "016", ["508"]), ("Springfield", "011", ["413"]), ("Cambridge", "021", ["617"]), ("Lowell", "018", ["978"])],
    "AZ": [("Phoenix", "850", ["602"]), ("Tucson", "857", ["520"]), ("Mesa", "852", ["480"]), ("Scottsdale", "852", ["480"]), ("Chandler", "852", ["480"])],
    "MD": [("Baltimore", "212", ["410", "443"]), ("Silver Spring", "209", ["301", "240"]), ("Rockville", "208", ["301", "240"]), ("Frederick", "217", ["301"]), ("Columbia", "210", ["410"])],
    "CO": [("Denver", "802", ["303", "720"]), ("Colorado Springs", "809", ["719"]), ("Aurora", "800", ["303", "720"]), ("Fort Collins", "805", ["970"]), ("Boulder", "803", ["303"])],
    "IN": [("Indianapolis", "462", ["317"]), ("Fort Wayne", "468", ["260"]), ("Evansville", "477", ["812"]), ("South Bend", "466", ["574"]), ("Carmel", "460", ["317"])],
    "TN": [("Nashville", "372", ["615"]), ("Memphis", "381", ["901"]), ("Knoxville", "379", ["865"]), ("Chattanooga", "374", ["423"])],
    "MO": [("St. Louis", "631", ["314"]), ("Kansas City", "641", ["816"]), ("Springfield", "658", ["417"]), ("Columbia", "652", ["573"])],
    "MN": [("Minneapolis", "554", ["612"]), ("St. Paul", "551", ["651"]), ("Rochester", "559", ["507"]), ("Duluth", "558", ["218"])],
    "WI": [("Milwaukee", "532", ["414"]), ("Madison", "537", ["608"]), ("Green Bay", "543", ["920"]), ("Kenosha", "531", ["262"])],
    "SC": [("Charleston", "294", ["843"]), ("Columbia", "292", ["803"]), ("Greenville", "296", ["864"]), ("Myrtle Beach", "295", ["843"])],
    "OR": [("Portland", "972", ["503", "971"]), ("Eugene", "974", ["541"]), ("Salem", "973", ["503"]), ("Gresham", "970", ["503"]), ("Bend", "977", ["541"])],
    "LA": [("New Orleans", "701", ["504"]), ("Baton Rouge", "708", ["225"]), ("Shreveport", "711", ["318"]), ("Lafayette", "705", ["337"]), ("Metairie", "700", ["504"])],
    "CT": [("Hartford", "061", ["860"]), ("New Haven", "065", ["203", "475"]), ("Stamford", "069", ["203", "475"]), ("Bridgeport", "066", ["203", "475"]), ("Waterbury", "067", ["203"])],
    "UT": [("Salt Lake City", "841", ["801", "385"]), ("Provo", "846", ["801"]), ("Ogden", "844", ["801"]), ("West Valley City", "841", ["801"]), ("Sandy", "840", ["801"])],
}

CITY_BASE_WEIGHTS = np.array([.36, .22, .16, .12, .08, .06], dtype=float)

EDUCATION = np.array([
    "Less than high school",
    "High school diploma/GED",
    "Some college - no degree",
    "Associate degree",
    "Bachelor degree",
    "Master degree",
    "Professional/Doctoral degree",
], dtype=object)

EDU_INCOME_MULT = {
    "Less than high school": .58,
    "High school diploma/GED": .75,
    "Some college - no degree": .88,
    "Associate degree": 1.00,
    "Bachelor degree": 1.30,
    "Master degree": 1.62,
    "Professional/Doctoral degree": 2.12,
}

HEADERS = [
    "customer_id", "first_name", "last_name", "gender", "date_of_birth",
    "address_line_1", "address_line_2", "street", "postal_code", "city",
    "state", "country", "phone_number", "email", "individual_yearly_income",
    "family_member_count", "resident_status", "resident_type", "education",
    "employment_status", "type_of_employment", "marital_status",
]


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def bounded_weights(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    values = np.maximum(values, 0)
    total = values.sum()
    if total <= 0:
        return np.full(len(values), 1 / len(values))
    return values / total


def choose_education(rng: np.random.Generator, age: int, bachelors_target: float) -> str:
    # Age-adjusted adult distribution, nudged by state bachelors+ target.
    if age < 21:
        p = np.array([.07, .40, .39, .07, .07, 0, 0])
    elif age < 25:
        p = np.array([.05, .27, .30, .12, .22, .035, .005])
    else:
        high = np.array([.62, .28, .10]) * bachelors_target
        low = np.array([.08, .32, .25, .12])
        low = low / low.sum() * (1 - bachelors_target)
        p = np.r_[low, high]
    p = bounded_weights(p)
    return str(rng.choice(EDUCATION, p=p))


def choose_marital_status(rng: np.random.Generator, age: int) -> str:
    u = rng.random()
    if age < 25:
        return "Married" if u < .12 else ("Separated/Divorced" if u < .15 else "Never married")
    if age < 35:
        return "Married" if u < .49 else ("Separated/Divorced" if u < .59 else ("Widowed" if u < .60 else "Never married"))
    if age < 55:
        return "Married" if u < .61 else ("Separated/Divorced" if u < .78 else ("Widowed" if u < .81 else "Never married"))
    if age < 70:
        return "Married" if u < .58 else ("Separated/Divorced" if u < .75 else ("Widowed" if u < .88 else "Never married"))
    return "Married" if u < .44 else ("Separated/Divorced" if u < .56 else ("Widowed" if u < .86 else "Never married"))


def choose_employment(rng: np.random.Generator, age: int) -> tuple[str, str]:
    u = rng.random()
    if age < 19:
        status = "Employed part-time" if u < .30 else ("Employed full-time" if u < .36 else ("Student" if u < .90 else "Unemployed - seeking work"))
    elif age < 25:
        status = "Employed full-time" if u < .43 else ("Employed part-time" if u < .64 else ("Student" if u < .78 else ("Unemployed - seeking work" if u < .85 else "Not in labor force")))
    elif age < 55:
        status = "Employed full-time" if u < .73 else ("Employed part-time" if u < .84 else ("Unemployed - seeking work" if u < .89 else ("Homemaker/Caregiver" if u < .94 else "Not in labor force")))
    elif age < 65:
        status = "Employed full-time" if u < .61 else ("Employed part-time" if u < .70 else ("Unemployed - seeking work" if u < .74 else ("Retired" if u < .88 else "Not in labor force")))
    elif age < 75:
        status = "Employed full-time" if u < .20 else ("Employed part-time" if u < .28 else ("Retired" if u < .86 else "Not in labor force"))
    else:
        status = "Employed full-time" if u < .05 else ("Employed part-time" if u < .09 else ("Retired" if u < .91 else "Not in labor force"))

    if status in {"Employed full-time", "Employed part-time"}:
        v = rng.random()
        employment_type = (
            "Private sector" if v < .73 else
            "Government" if v < .84 else
            "Nonprofit" if v < .90 else
            "Self-employed" if v < .98 else
            "Gig/contract"
        )
    else:
        employment_type = "Not applicable"
    return status, employment_type


def choose_family_count(rng: np.random.Generator, age: int, marital: str) -> int:
    adults = 2 if marital == "Married" else 1
    if rng.random() < (.14 if age < 30 else .07):
        adults += 1

    if 25 <= age < 45:
        child_prob = .55
    elif 45 <= age < 55:
        child_prob = .28
    elif age < 25:
        child_prob = .10
    else:
        child_prob = .06

    children = 0
    if rng.random() < child_prob:
        children = 1 + int(rng.binomial(3, .33))
    return int(min(8, adults + children))


def make_dob(rng: np.random.Generator, age: int, as_of: date) -> str:
    # Exact day precision is not needed for the synthetic population; this creates
    # a valid DOB consistent with the chosen age at the as-of date.
    year = as_of.year - age
    month = int(rng.integers(1, 13))
    if month == 2:
        max_day = 28
    elif month in {4, 6, 9, 11}:
        max_day = 30
    else:
        max_day = 31
    day = int(rng.integers(1, max_day + 1))
    dob = date(year, month, day)
    # If birthday has not occurred yet, shift one year earlier to preserve age.
    if (dob.month, dob.day) > (as_of.month, as_of.day):
        dob = date(year - 1, month, day)
    return dob.isoformat()


def build_name_pools(seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    fake = Faker("en_US")
    Faker.seed(seed)
    male = np.array([fake.first_name_male().replace(",", "") for _ in range(2400)], dtype=object)
    female = np.array([fake.first_name_female().replace(",", "") for _ in range(2400)], dtype=object)
    neutral = np.array([fake.first_name().replace(",", "") for _ in range(1000)], dtype=object)
    last = np.array([fake.last_name().replace(",", "") for _ in range(5000)], dtype=object)
    return male, female, neutral, last


def build_street_pool() -> np.ndarray:
    first = ["Maple", "Cedar", "Oak", "Pine", "Willow", "Lake", "Hill", "River", "Sunset", "Park", "Meadow", "Forest", "Spring", "Valley", "Liberty", "Heritage", "Union", "Grand", "Highland", "Ridge", "Garden", "Brook", "Stone", "Magnolia", "Sycamore"]
    second = ["View", "Ridge", "Grove", "Point", "Heights", "Crossing", "Run", "Bend", "Trail", "Creek", "Field", "Gate", "Park", "Hollow", "Terrace", "Vista"]
    suffix = ["St", "Ave", "Rd", "Blvd", "Ln", "Dr", "Ct", "Way", "Pkwy", "Ter"]
    streets = [f"{a} {b} {c}" for a in first for b in second for c in suffix[:5]]
    return np.array(streets, dtype=object)


# -----------------------------------------------------------------------------
# Main generator
# -----------------------------------------------------------------------------
def generate(args: argparse.Namespace) -> None:
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out_file = outdir / args.output
    sample_file = outdir / args.sample_output
    summary_file = outdir / args.summary_output

    rng = np.random.default_rng(args.seed)
    random.seed(args.seed)

    state_codes = list(URBAN)
    state_weights = bounded_weights(np.array([URBAN[s][1] for s in state_codes], dtype=float))
    name_m, name_f, name_n, last_names = build_name_pools(args.seed)
    streets = build_street_pool()

    # Adult-customer age bands; customer master is intentionally an adult
    # historical customer/prospect universe, not a full population register.
    age_bands = [(18, 24), (25, 34), (35, 44), (45, 54), (55, 64), (65, 74), (75, 84), (85, 90)]
    age_weights = np.array([.11, .19, .18, .17, .16, .11, .06, .02])

    state_counter = Counter()
    gender_counter = Counter()
    employment_counter = Counter()
    income_sum = 0.0
    family_sum = 0
    sample_rows: list[list[object]] = []
    as_of = date(2025, 12, 31)

    opener = gzip.open if str(out_file).endswith(".gz") else open
    with opener(out_file, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADERS)

        for i in range(1, args.n_customers + 1):
            st = str(rng.choice(state_codes, p=state_weights))
            state_name, _, percent_urban = URBAN[st]
            median_income, female_share, bachelors_target, foreign_born = STATE_CFG[st]

            # State older-population nudge while retaining the overall adult mix.
            local_age_w = age_weights.copy()
            if st in {"FL", "PA", "MI", "OH", "CT", "OR"}:
                local_age_w *= np.array([.92, .95, .98, 1.00, 1.05, 1.11, 1.13, 1.12])
            elif st in {"UT", "TX", "GA", "NC"}:
                local_age_w *= np.array([1.12, 1.08, 1.04, 1.00, .94, .88, .84, .80])
            local_age_w = bounded_weights(local_age_w)
            band = age_bands[int(rng.choice(len(age_bands), p=local_age_w))]
            age = int(rng.integers(band[0], band[1] + 1))

            nb_rate = .018 if age < 30 else (.010 if age < 50 else .005)
            u = rng.random()
            if u < nb_rate:
                gender = "Non-binary/Other"
            elif u < nb_rate + (1 - nb_rate) * female_share:
                gender = "Female"
            else:
                gender = "Male"

            education = choose_education(rng, age, bachelors_target)
            marital = choose_marital_status(rng, age)
            employment_status, type_of_employment = choose_employment(rng, age)
            family_count = choose_family_count(rng, age, marital)

            # Income: correlated with state, age, education and employment.
            edu_mult = EDU_INCOME_MULT[education]
            if age < 25:
                age_mult = .62
            elif age < 35:
                age_mult = .92
            elif age < 45:
                age_mult = 1.08
            elif age < 55:
                age_mult = 1.17
            elif age < 65:
                age_mult = 1.10
            elif age < 75:
                age_mult = .78
            else:
                age_mult = .55

            state_factor = median_income / 83730.0
            base = 54000 * state_factor * age_mult * edu_mult
            income = base * rng.lognormal(mean=0, sigma=.43)
            if employment_status == "Employed part-time":
                income *= .50
            elif employment_status == "Student":
                income *= rng.uniform(.05, .25)
            elif employment_status == "Unemployed - seeking work":
                income *= rng.uniform(.03, .22)
            elif employment_status == "Homemaker/Caregiver":
                income *= rng.uniform(.02, .16)
            elif employment_status == "Not in labor force":
                income *= rng.uniform(.03, .20)
            elif employment_status == "Retired":
                income = rng.lognormal(math.log(max(14000, 30000 * state_factor)), .48)
            if rng.random() < .004 and employment_status in {"Employed full-time", "Employed part-time"}:
                income *= rng.uniform(2.2, 5.5)
            income = int(round(float(np.clip(income, 0, 2_000_000)) / 100) * 100)

            # Citizenship/residency vocabulary matches the demographic generator.
            r = rng.random()
            if r < 1 - foreign_born:
                resident_status = "Citizen by birth"
            elif r < 1 - foreign_born + foreign_born * .52:
                resident_status = "Naturalized citizen"
            elif r < 1 - foreign_born + foreign_born * .83:
                resident_status = "Permanent resident"
            else:
                resident_status = "Temporary/other non-citizen"

            core = float(np.clip(.47 + (percent_urban - 80) / 180, .40, .58))
            inner = .34
            outer = 1 - core - inner
            resident_type = str(rng.choice(
                ["Urban core", "Inner suburban", "Outer suburban/peri-urban"],
                p=[core, inner, outer],
            ))

            city_items = CITIES[st]
            cw = bounded_weights(CITY_BASE_WEIGHTS[:len(city_items)])
            city, zip_prefix, area_codes = city_items[int(rng.choice(len(city_items), p=cw))]
            postal_code = f"{zip_prefix}{int(rng.integers(0, 100)):02d}"
            phone = f"+1-{str(rng.choice(area_codes))}-555-{int(rng.integers(100, 200)):04d}"

            street = str(streets[int(rng.integers(0, len(streets)))])
            address1 = f"{int(rng.integers(1, 10000))} {street}"
            a = rng.random()
            address2 = f"Apt {int(rng.integers(1, 1000))}" if a < .24 else (f"Unit {int(rng.integers(1, 1000))}" if a < .32 else "")

            if gender == "Male":
                first_name = str(name_m[int(rng.integers(0, len(name_m)))])
            elif gender == "Female":
                first_name = str(name_f[int(rng.integers(0, len(name_f)))])
            else:
                first_name = str(name_n[int(rng.integers(0, len(name_n)))])
            last_name = str(last_names[int(rng.integers(0, len(last_names)))])

            customer_id = f"CUS{i:09d}"
            domain = ["example.com", "example.net", "example.org"][i % 3]
            email = f"customer{i:09d}@{domain}"
            dob = make_dob(rng, age, as_of)

            row = [
                customer_id, first_name, last_name, gender, dob,
                address1, address2, street, postal_code, city, state_name,
                "United States", phone, email, income, family_count,
                resident_status, resident_type, education, employment_status,
                type_of_employment, marital,
            ]
            writer.writerow(row)

            if len(sample_rows) < args.sample_rows:
                sample_rows.append(row)

            state_counter[state_name] += 1
            gender_counter[gender] += 1
            employment_counter[employment_status] += 1
            income_sum += income
            family_sum += family_count

            if i % 25000 == 0 or i == args.n_customers:
                print(f"Generated {i:,}/{args.n_customers:,} customers")

    with open(sample_file, "w", encoding="utf-8", newline="") as sf:
        sw = csv.writer(sf)
        sw.writerow(HEADERS)
        sw.writerows(sample_rows)

    summary = {
        "rows": args.n_customers,
        "columns": len(HEADERS),
        "seed": args.seed,
        "output": str(out_file),
        "sample_output": str(sample_file),
        "customer_id_start": "CUS000000001",
        "customer_id_end": f"CUS{args.n_customers:09d}",
        "mean_individual_yearly_income": round(income_sum / args.n_customers, 2),
        "mean_family_member_count": round(family_sum / args.n_customers, 3),
        "gender_distribution": {k: round(v / args.n_customers, 6) for k, v in gender_counter.items()},
        "employment_distribution": {k: round(v / args.n_customers, 6) for k, v in employment_counter.items()},
        "state_distribution": {k: round(v / args.n_customers, 6) for k, v in state_counter.items()},
        "independence_rule": "No person_id exists in this file and no row is copied from the demographic universe. customer_id is a separate namespace.",
        "feature_compatibility": "Shared categorical fields intentionally use the same vocabulary as the demographic scoring universe.",
        "contact_safety": "Emails use IANA-reserved example domains; phones use fictional 555-0100..0199 numbers; street addresses are algorithmically synthesized.",
    }
    with open(summary_file, "w", encoding="utf-8") as jf:
        json.dump(summary, jf, indent=2)

    print(f"\nDONE\nCustomer master: {out_file}\nSample: {sample_file}\nSummary: {summary_file}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate synthetic U.S. customer master data")
    p.add_argument("--n-customers", type=int, default=125_000)
    p.add_argument("--seed", type=int, default=20260819)
    p.add_argument("--outdir", default="./output")
    p.add_argument("--output", default="customer_master_125000.csv.gz")
    p.add_argument("--sample-output", default="customer_master_sample_10000.csv")
    p.add_argument("--summary-output", default="customer_master_summary.json")
    p.add_argument("--sample-rows", type=int, default=10_000)
    return p.parse_args()


if __name__ == "__main__":
    generate(parse_args())
