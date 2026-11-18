# Heat pump feasibility for NYC buildings

Estimates, for each LL84-reporting building:

1. **How hard a heat pump switch is** (feasibility tier 1 to 3, with reasons)
2. **How much electricity heat pumps would add** (yearly kWh and design-day peak kW, air-source and ground-source)
3. **Whether the building and its neighborhood can handle it** (electrical headroom ratio, added peak by NTA and citywide)

Part of the question: *Which buildings should be prioritized for decarbonization to maximize carbon emissions reductions from natural gas per dollar invested?*

## Folder layout

```
heat_pump_feasibility/
├── README.md
├── requirements.txt
├── docs/
│   └── methods.md          formulas, assumptions, data cleaning log
├── data/
│   ├── raw/                downloaded files (not committed to git)
│   └── processed/          pipeline outputs
├── hpf/
│   ├── config.py           column names + every assumption (edit here)
│   ├── download.py         step 1: download datasets
│   ├── inspect.py          step 2: check column names
│   ├── utils.py            helpers (column names, BBL cleaning, numbers)
│   ├── load.py             clean each dataset
│   ├── calcs.py            space-heating split, heat pump load, peaks, headroom
│   ├── tiers.py            feasibility tier rules
│   └── run.py              step 3: run everything
└── tests/
    └── test_calcs.py       checks the formulas
```

## Setup

```bash
cd heat_pump_feasibility
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python -m hpf.download        # 1. download datasets into data/raw/  (large; can take a while)
python -m hpf.inspect         # 2. check column names; fix any MISSING in hpf/config.py
python -m hpf.run             # 3. run the pipeline
pytest                        # optional: check the formulas
```

To use a local file instead of the download (for example the LL87 Excel file):

```bash
python -m hpf.run --ll87 path/to/LL87_2019-2024.xlsx
```

## Datasets

| Dataset | NYC Open Data ID | Used for |
|---|---|---|
| LL84 Benchmarking, 2023 to present | `5zyy-y8am` | Building type, floor area, yearly gas/oil/steam/electricity, NTA |
| LL84 Monthly Data | `fvp3-gcb2` | Split gas into space heating vs. hot water/cooking; summer and winter electricity peaks |
| LL87 Energy Audits | `au6c-jqvf` | Heating plant type (steam vs. hot water), boiler efficiency |
| PLUTO | `64uk-42ks` | Landmark/historic district, lot area, floors, year built |

All joins use **BBL** (10-digit tax lot ID), except monthly to annual LL84, which uses **Property ID**.

## Outputs (`data/processed/`)

| File | Contents |
|---|---|
| `hp_feasibility_buildings.csv` | One row per building, all estimates and the tier |
| `hp_feasibility_by_type.csv` | Counts, added kWh and peak MW by building type and tier |
| `hp_grid_by_nta.csv` | Added winter peak by neighborhood |
| `hp_grid_citywide.csv` | Citywide added peak and energy, air-source vs. ground-source |

Key columns in the building file:

| Column | Meaning |
|---|---|
| `fuel_space_kbtu` / `fuel_base_kbtu` | Fossil fuel for space heating / for hot water and cooking |
| `space_split_method` | `monthly` (from LL84 monthly) or `default_share` (assumed by type) |
| `hp_kwh_ashp`, `hp_kwh_gshp` | Yearly heat pump electricity |
| `hp_peak_kw_ashp`, `hp_peak_kw_gshp` | Heat pump electricity on the coldest design day |
| `headroom_R_ashp` | (current winter peak + heat pump peak) / current summer peak. ≤1 fits, >1.5 major upgrade |
| `feasibility_tier` | 1 easy, 2 moderate, 3 hard, blank = excluded (no on-site fossil heating) |
| `tier_reason` | Hard factors, then (moderate factors) in parentheses |
| `data_confidence` | high = LL87 + monthly data, medium = one, low = neither |

## Assumptions to verify before reporting results

All live in `hpf/config.py`:

- NYC heating degree days (4,700) and design temperature (15°F): check NOAA and ASHRAE
- Heat pump efficiency (SCOP and cold-day COP): check with Prof. Gevelber
- Default boiler efficiencies and space-heating shares by type
- Monthly load factors by building type (test 0.4 to 0.6)
- Tier thresholds (headroom 1.0 / 1.5, open lot 500 sq ft, pre-1950 = steam)
