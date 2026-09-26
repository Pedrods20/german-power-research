# German Power Market Research

**Day-ahead prices, solar capture and battery dispatch in Germany–Luxembourg.**

Independent research by **Pedro Cabral**, Senior Specialist in Power & Renewables at S&P Global Energy, covering Brazil, Chile and Argentina.

This project examines how the daily price profile has changed and whether better price forecasts improve battery dispatch margins.

**[Explore the analysis](https://pedrods20.github.io/german-power-research/)** · [Forecast results](https://pedrods20.github.io/german-power-research/forecast) · [Battery economics](https://pedrods20.github.io/german-power-research/battery)

## Key findings

| Finding | Evidence from the study | Commercial relevance |
|---|---|---|
| The on-peak premium has turned negative | On-peak minus off-peak: **+€10.6/MWh in 2019 → −€13.7/MWh in 2026 YTD** | Block averages can mask the hourly opportunities and constraints relevant to storage. |
| Solar capture has deteriorated | Solar capture rate: **93% → 51%** over the same period | Generation timing matters for renewable revenues and exposure to low midday prices. |
| Better forecasts add modest dispatch value | **24.3% lower hourly MAE** versus the strongest naive price benchmark; approximately **€4,400/MW/year** additional simulated margin versus the strongest fixed naive dispatch strategy | Forecast accuracy needs to be assessed through its effect on decisions and margins. |

The price and dispatch benchmarks are selected separately. The battery result refers to a **1 MW / 4 MWh** asset and expresses the historical average daily increment on a 365.25-day basis; it is not a forecast of annual earnings.

Ridge-based dispatch underperformed its strongest fixed naive comparator on **827 of 2,404 eligible days**. Most of its simulated gross margin was also captured by the simple strategy. The detailed analysis reports downside, concentration of gains and sensitivity to costs, efficiency, downtime and a second daily charge–discharge episode.

## Explore the work

| Page | Focus |
|---|---|
| [Market view](https://pedrods20.github.io/german-power-research/) | Price shape, capture rates, negative prices and storage capacity |
| [Forecast evidence](https://pedrods20.github.io/german-power-research/forecast) | Ridge, LightGBM and three naive benchmarks; performance across market regimes |
| [Storage value](https://pedrods20.github.io/german-power-research/battery) | Dispatch margins, incremental forecast value and sensitivity cases |
| [Methodology](https://pedrods20.github.io/german-power-research/methodology) | Data sources, assumptions, evaluation protocol and reproduction instructions |

## Scope and limitations

- **Periods:** the market-data export is dated **15 September 2026**. The forecast evaluation covers **3 January 2020–12 September 2026**. Market figures for 2026 are year-to-date and sensitive to seasonality.
- **Research status:** retrospective development results on history already inspected. A prospective pilot is tracked separately; the backtest is not a live trading record.
- **Battery:** 1 MW / 4 MWh, 90% round-trip efficiency, at most one charge–discharge episode per day, and zero initial and terminal state of charge. Headline margins exclude operating, degradation and capital costs. Separate sensitivities use illustrative variable costs.
- **Coverage:** day-ahead arbitrage at bidding-zone level. Intraday trading, balancing services, imbalance settlement and market impact are outside scope. Hourly averages do not represent individual 15-minute products.
- **Evidence:** historical inputs contain provider revisions, rather than verified publication-time snapshots. Market co-movements do not establish causation or future profitability.

**Data:** [Energy-Charts / Fraunhofer ISE](https://www.energy-charts.info/), including figures redistributed from ENTSO-E and SMARD. See the [methodology](site/methodology.md) for attribution and definitions.

## About me

I am a Senior Specialist in Power & Renewables at S&P Global Energy, covering Brazil, Chile and Argentina. My work focuses on electricity market fundamentals, price formation and the commercial implications of the energy transition.

This independent project extends my research to European power markets, examining German day-ahead prices and the value of forecasting for battery dispatch.

[GitHub profile](https://github.com/Pedrods20)

<details>
<summary>Reproduce the analysis</summary>

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
gpa validate
gpa export
npm ci
npm run build
```

Windows PowerShell activation: `.venv\Scripts\Activate.ps1`.

The repository includes the versioned data, frozen historical experiments and analysis. Detailed assumptions and validation procedures are documented in [Methodology](site/methodology.md).

</details>

Code: [MIT](LICENSE). Underlying data remains subject to provider terms.
