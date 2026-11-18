# Price of switch

Estimated cost for each building to replace on-site gas or oil heating with heat pumps,
for air-source (`ashp`) and ground-source (`gshp`). Code: `hpf/price.py`. All numbers: `hpf/config.py`.

## Formula

For each building $i$ and heat pump type:

$$\text{low}_i = U_i \cdot c^{\text{unit}}_{\text{low}} + A^{\text{nonres}}_i \cdot c^{\text{sqft}}_{\text{low}} \qquad \text{high}_i = U_i \cdot c^{\text{unit}}_{\text{high}} + A^{\text{nonres}}_i \cdot c^{\text{sqft}}_{\text{high}}$$

$$\text{mid}_i = \text{low}_i + p_i \, (\text{high}_i - \text{low}_i)$$

$$\text{net}_i = \max\big(0,\; \text{mid}_i - I_i - B_i\big)$$

| Symbol | Meaning |
|---|---|
| $U_i$ | Apartments priced per unit (multifamily and the residential part of mixed use) |
| $A^{\text{nonres}}_i$ | Non-residential floor area, priced per sq ft |
| $c$ | Cost range from the source report (see below) |
| $p_i$ | Position in the cost range, 0 (low end) to 1 (high end) |
| $I_i$ | Incentives, capped at 50% of $\text{mid}_i$ |
| $B_i$ | Boiler credit: cost of a new boiler, if the boiler is due within 5 years |

## Inputs and sources

| Input | Value | Source |
|---|---|---|
| Multifamily, 2 to 19 units | ASHP \$13,000 to \$30,100 per unit; GSHP \$29,600 to \$42,900 | Rosen Consulting Group (2022) |
| Multifamily, 20+ units | ASHP \$19,400 to \$42,900 per unit; GSHP \$40,800 to \$56,000 | Rosen Consulting Group (2022) |
| Office | ASHP \$12 to \$21 per sq ft; GSHP \$17 to \$24 | Rosen Consulting Group (2022) |
| Other non-residential | Office rate used as a stand-in | Assumption |
| Incentive, multifamily | \$5,000 per unit (market rate) | Con Edison Clean Heat |
| Incentive, commercial | \$120 per MMBtu of space-heating fuel | Con Edison Clean Heat (basis to verify) |
| New boiler cost | \$3.29 per sq ft | Median LL87 "Replace boiler" estimate (559 audits) |
| Boiler lifespan | 30 years | Assumption (typical 25 to 35) |

Rosen Consulting Group, *New York Building Electrification and Decarbonization Costs* (June 2022, draft),
commissioned by the NYS Association of REALTORS and submitted as public comment. Costs may lean high.

## Position in the cost range ($p_i$)

Starts at 0.5, then shifts (assumptions, to verify with Prof. Gevelber):

| Condition | Shift |
|---|---|
| Steam distribution (observed or assumed) | +0.30 |
| Hot water or ducted system | −0.30 |
| Major electrical upgrade likely ($R > 1.5$) | +0.15 |
| Electrical upgrade possible ($1.1 < R \le 1.5$) | +0.05 |
| Landmark or historic district | +0.10 |
| Mixed use | +0.05 |

## Unit counts

LL84 unit count first, PLUTO as fallback. A count is replaced by
residential floor area ÷ 900 sq ft when it implies apartments under 300 sq ft (too many units,
often a PLUTO count for a whole multi-building lot) or over 3,000 sq ft (too few units).
These buildings have `units_estimated = True` and `cost_basis = per_unit_estimated`.

## Output columns (in `hp_feasibility_buildings.csv`)

| Column | Meaning |
|---|---|
| `price_ashp_low`, `_mid`, `_high` | Gross cost range (before incentives and boiler credit), \$ |
| `incentive_ashp` | Incentive subtracted, \$ |
| `boiler_due_soon`, `avoided_boiler_credit` | Whether the boiler credit applies, and its amount, \$ |
| `price_ashp_net` | Net price: mid − incentive − boiler credit, floored at \$0 |
| `price_ashp_net_per_sqft` | Net price per sq ft of floor area |
| `price_ashp_net_is_zero` | True when incentives + boiler credit covered the whole cost |
| (same with `gshp`) | Ground-source versions |
| `cost_basis` | `per_unit`, `per_unit_estimated`, `per_sqft` (office), `per_sqft_office_proxy`, or combinations |
| `units_priced`, `units_estimated`, `nonres_sqft_priced` | What was priced |
| `range_position`, `price_drivers` | $p_i$ and the conditions that set it |
| `price_confidence` | high / medium / low (below). Blank = excluded |

Excluded buildings (no on-site fossil heating) have blank price columns.

## Price confidence

One point each for:
1. A solid cost basis: reported, plausible unit count, or an office priced per sq ft
2. A known heating system: steam, hot water, or ducted, from LL87 or a permit (not assumed)

2 points = high, 1 = medium, 0 = low.

## Using the price in a score

- **Gross vs. net:** `price_ashp_mid` is the total retrofit cost; `price_ashp_net` is the cost to the owner.
  Net can be \$0 (`price_ashp_net_is_zero`), which makes cost per ton \$0. Use gross, or handle zeros.
- **Upfront vs. yearly:** price is a one-time cost; emissions saved is per year. Cost per ton needs a lifetime $L$:
  $\text{cost per ton}_i = \text{price}_i / (\Delta E_i \times L)$.
- **Same retrofit on both sides:** price assumes heat pumps replace space heating only (`fuel_space_kbtu`).
  Emissions saved should use the same scope.

## Known limitations

- Multifamily comes out about 2 times more expensive per sq ft than office, from the source report's numbers.
- Non-office, non-residential buildings use the office rate.
- The boiler credit needs an install year; permit dates are not yet available.
- Decommissioning the old system and incentives for affordable housing (up to \$14,000/unit) are not included.
