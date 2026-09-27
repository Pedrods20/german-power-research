# German Power Market Research

**Day-ahead prices, solar capture and battery dispatch in Germany–Luxembourg.**

Independent research by **Pedro Cabral**, a power market analyst with experience in Latin American electricity markets.

This project measures how solar reshaped the German day-ahead price, what that shape is worth to a battery, and when a price forecast adds to simple scheduling rules.

**[Explore the analysis](https://pedrods20.github.io/german-power-research/)** · [Forecast results](https://pedrods20.github.io/german-power-research/forecast) · [Battery economics](https://pedrods20.github.io/german-power-research/battery)

## Key findings

| Finding | Evidence from the study | Commercial relevance |
|---|---|---|
| The recurring price shape carries most of the arbitrage value | A rule that repeats the last similar day captured **81% → 93%** of the perfect-foresight margin (2020 → 2026 YTD) | Most day-ahead value needs no model; a forecast competes against a strong free baseline. |
| A forecast earns when the shape breaks | **24.3% lower hourly MAE** than the best naive forecast, worth about **€4,400/MW/year**; **77%** of that gain comes from the most atypical fifth of days, and on the most typical 40% it loses | Forecast value is conditional, which points to a switch rather than an always-on model. |
| Solar has inverted the daily price shape | On-peak premium **+€10.6 → −€13.7/MWh**; daily price range **80% → 146%** of the average price; solar capture **93% → 51%** (2019 → 2026 YTD) | Block averages mask the hourly spread that storage is paid for. |
| Balancing pays more per MW, but it is shallow | aFRR capacity **€649** and FCR **€407/MW/day** against **€294** for day-ahead arbitrage (Nov 2020–Sep 2026); arbitrage rose from **34% to 74%** of the aFRR value (2021 → 2026) | About 0.6 GW of FCR and 2 GW of aFRR each way cannot absorb a 21 GW battery fleet; arbitrage is the market that scales. |
| 15-minute products add modestly | Quarter-hour dispatch raises the arbitrage ceiling by **4% (4-hour) to 9% (1-hour)** | The finer products are worth most to short-duration assets. |

The price and dispatch benchmarks are selected separately. Battery results refer to a **1 MW / 4 MWh** asset unless stated, and annual figures are historical daily averages on a 365.25-day basis, not forecasts of annual earnings. Balancing figures are capacity payments only.

Ridge-based dispatch underperformed its strongest fixed naive comparator on **827 of 2,404 eligible days**. Most of its simulated gross margin was also captured by the simple strategy. The detailed analysis reports downside, concentration of gains and sensitivity to costs, efficiency, downtime and a second daily charge–discharge episode.

## Explore the work

| Page | Focus |
|---|---|
| [Market view](https://pedrods20.github.io/german-power-research/) | The shape against the forecast, why the shape exists, and the balancing and 15-minute alternatives |
| [Forecast evidence](https://pedrods20.github.io/german-power-research/forecast) | Ridge, LightGBM and three naive benchmarks; whether each picks the right hours; performance across market regimes |
| [Storage value](https://pedrods20.github.io/german-power-research/battery) | Dispatch margins, where the forecast earns, 15-minute value, the balancing revenue stack and sensitivity cases |
| [Methodology](https://pedrods20.github.io/german-power-research/methodology) | Data sources, assumptions, evaluation protocol and reproduction instructions |

## Scope and limitations

- **Periods:** the market-data export is dated **15 September 2026**. The forecast evaluation covers **3 January 2020–12 September 2026**. Market figures for 2026 are year-to-date and sensitive to seasonality.
- **Research status:** retrospective development results on history already inspected. A prospective pilot is tracked separately; the backtest is not a live trading record.
- **Battery:** 1 MW / 4 MWh, 90% round-trip efficiency, at most one charge–discharge episode per day, and zero initial and terminal state of charge. Headline margins exclude operating, degradation and capital costs. Separate sensitivities use illustrative variable costs.
- **Coverage:** day-ahead arbitrage at bidding-zone level, compared with FCR and aFRR capacity revenue. Continuous intraday trading is not modelled, for want of a free public price source; activation energy, imbalance settlement and market impact are also outside scope. The forecast is hourly; a separate study values 15-minute products.
- **Evidence:** historical inputs contain provider revisions, rather than verified publication-time snapshots. Market co-movements do not establish causation or future profitability.

**Data:** [Energy-Charts / Fraunhofer ISE](https://www.energy-charts.info/), including figures redistributed from ENTSO-E and SMARD, and balancing auction results from [regelleistung.net](https://www.regelleistung.net/). See the [methodology](site/methodology.md) for attribution and definitions.

## About me

I am a power market analyst with experience covering Brazil, Chile and Argentina. My work focuses on electricity market fundamentals, price formation and the commercial implications of the energy transition.

This independent project extends my research to European power markets, examining German day-ahead prices and the value of forecasting for battery dispatch.

[GitHub profile](https://github.com/Pedrods20)

<details>
<summary>Reproduce the analysis</summary>

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
gpa validate
gpa balancing            # FCR and aFRR auction results; slow on the first run
gpa quarter-hour-study   # the 15-minute value study
gpa export
npm ci
npm run build
```

Windows PowerShell activation: `.venv\Scripts\Activate.ps1`.

The repository includes the versioned data, frozen historical experiments and analysis. Detailed assumptions and validation procedures are documented in [Methodology](site/methodology.md).

</details>

Code: [MIT](LICENSE). Underlying data remains subject to provider terms.
