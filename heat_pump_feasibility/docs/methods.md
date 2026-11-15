# Methods: heat pump feasibility

## 1. Building selection
- LL84 annual, most recent year per Property ID.
- Excluded from tiers: buildings using more district steam than on-site fossil fuel, buildings with no fossil fuel, and LL87 plant type "Utility District Steam".

## 2. Building type
From LL84 "Largest Property Use Type" (keyword groups in `config.TYPE_GROUPS`):
multifamily, office, industrial, food_service, other.
If the 2nd largest use is ≥ 20% of floor area: mixed_use.

## 3. Space heating vs. other gas use
Summer gas (June to August) = hot water + cooking.

$$G_{\text{base}} = 12 \times \overline{G}_{\text{summer}} \qquad \text{share}_{\text{space}} = 1 - \frac{G_{\text{base}}}{G_{\text{annual}}}$$

The share is applied to LL84 yearly fossil fuel (gas + #2 + #4 oil).
No monthly data, or mainly oil: default share by type (`config.SPACE_HEAT_SHARE_DEFAULT`).

## 4. Heat pump electricity
$$Q = F_{\text{space}} \times \eta_{\text{boiler}} \qquad K_{\text{HP}} = \frac{Q}{\text{SCOP} \times 3.412}$$

$\eta_{\text{boiler}}$ from LL87 "Rated Efficiency: Heating Plant 1" (values over 1 divided by 100; values outside 0.5 to 1.0 dropped), otherwise default by distribution type.

## 5. Design-day peak
$$UA = \frac{Q}{24 \times \text{HDD}} \qquad P_{\text{HP}} = \frac{UA \times (T_{\text{balance}} - T_{\text{design}})}{\text{COP}_{\text{cold}} \times 3.412}$$

## 6. Current peaks and headroom
$$P_{\text{season}} = \frac{\max \text{ monthly kWh in season}}{730 \times LF} \qquad R = \frac{P_{\text{winter}} + P_{\text{HP}}}{P_{\text{summer}}}$$

No monthly data: both peaks = annual kWh / (8760 × LF).
Reasoning: electrical service is sized for the current (usually summer) peak, so a new winter peak below it likely needs no service upgrade.

## 7. Tiers
| Hard factors | Moderate factors |
|---|---|
| Steam distribution (LL87, or assumed if built before 1950 with no LL87 data) | Headroom 1.0 < R ≤ 1.5 |
| R > 1.5 | Distribution unknown |
| Landmark or historic district | Mixed use |
| Industrial / food service, or space-heating share < 50% | |

Tier 1: none. Tier 2: one hard factor, or only moderate. Tier 3: two or more hard factors.
`gshp_space_ok`: open lot (lot area − bldg area / floors) ≥ 500 sq ft.

## 8. Known limitations
- LL87 covers buildings over 50,000 sq ft only so the others rely on assumptions.
- Load factors, COPs, and climate constants are assumptions.
- Headroom estimates building service only. Excludes Con Ed network capacity.
- Hot water is left on fossil fuel in this version (`fuel_base_kbtu`).

## Data cleaning log
(Record each cleaning decision here with the date and the number of rows affected.)
