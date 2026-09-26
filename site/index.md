---
title: Market view
---

# German power: price shape and battery value

```js
const yearly = [...await FileAttachment("data/capacity_price_yearly.parquet").parquet()]
  .filter((d) => d.zone === "DE-LU")
  .sort((a, b) => a.year.localeCompare(b.year));
const shape = [...await FileAttachment("data/price_shape.parquet").parquet()];
const marginYearly = [...await FileAttachment("data/battery_margin_yearly.parquet").parquet()];
const capacity = [...await FileAttachment("data/capacity.parquet").parquet()];
const ledgerStatus = await FileAttachment("data/ledger_status.json").json();
const ridgeArm = ledgerStatus.arms.find((d) => d.model === "ridge");
const ledgerDate = ledgerStatus.as_of ? ledgerStatus.as_of.slice(0, 10) : "this build";
const yearlyCap = capacity.filter((d) => d.time_step === "yearly" && !d.is_planned);
const capAt = (technology, period) => yearlyCap.find((d) => d.technology === technology && String(d.period) === period);
const pumped = yearlyCap
  .filter((d) => d.technology === "Hydro pumped storage")
  .sort((a, b) => String(a.period).localeCompare(String(b.period)));
const pumpedFirst = pumped[0];
const pumpedLast = pumped[pumped.length - 1];
const fleetHours = (period) => {
  const power = capAt("Battery storage (power)", period);
  const energy = capAt("Battery storage (capacity)", period);
  return power && energy && power.value ? energy.value / power.value : null;
};
const first = yearly[0];
const last = yearly[yearly.length - 1];
const latestFull = yearly[yearly.length - 2];
const crisis = yearly.find((d) => d.year === "2022");
const foresight4 = marginYearly
  .filter((d) => d.strategy === "perfect_foresight" && d.energy_mwh === 4)
  .sort((a, b) => a.year.localeCompare(b.year));
const fleetFirst = foresight4[0];
const fleetLast = foresight4[foresight4.length - 1];
const foresight = (period) => foresight4.find((d) => d.year === period);
const eur = (v) => v.toLocaleString("en", {maximumFractionDigits: 0});
const num = (v) => v.toFixed(1);
const pct = (v) => `${v.toFixed(0)}%`;
const rate = (v) => v.toFixed(2);
```

Solar has moved the German price peak from midday to the evening. This note
measures the shift in Germany–Luxembourg (DE-LU) day-ahead prices, values it for
a battery, and tests how much a price forecast adds to simple scheduling rules.

**DE-LU, ${first.year} → ${last.year} YTD** · on-peak premium **EUR
${num(first.spread)} → ${num(last.spread)}/MWh** · daily price range
**${pct(first.intraday_spread_pct_of_price)} → ${pct(last.intraday_spread_pct_of_price)}**
of the average price · solar capture rate **${rate(first.solar_capture_rate)} →
${rate(last.solar_capture_rate)}** · negative-price hours **${num(first.negative_pct)}%
→ ${num(last.negative_pct)}%**

[Forecast evidence](./forecast) · [Storage value](./battery) · [Methodology](./methodology)

## 1. The on-peak premium has turned negative

In ${first.year}, the on-peak block (08:00–20:00 on weekdays) cleared EUR
${num(first.spread)}/MWh above off-peak. In ${last.year} it clears EUR
${num(Math.abs(last.spread))}/MWh below it. Installed solar rose from
${num(first.solar_capacity_gw)} to ${num(last.solar_capacity_gw)} GW, and the
price solar plants earn fell from ${rate(first.solar_capture_rate)} to
${rate(last.solar_capture_rate)} of the average price. Wind's capture rate barely
moved (${rate(first.wind_capture_rate)} → ${rate(last.wind_capture_rate)}): wind
output is spread across the day, while solar arrives in the same hours at every
plant.

The block definition is part of the story. Drawn when demand shaped the day, it
now contains both the cheapest midday hours and the start of the evening ramp, so
its average says less each year. The daily high–low range, which does not depend
on when the extremes occur, is the better measure of what flexibility is paid.

## 2. The daily range widened: a change in shape, not in price level

```js
const spreadSeries = yearly.flatMap((d) => [
  {year: d.year, metric: "On-peak minus off-peak block", value: d.spread_pct_of_price},
  {year: d.year, metric: "Daily high minus low", value: d.intraday_spread_pct_of_price},
]);
```

```js
Plot.plot({
  title: "The block premium fell as the daily range widened",
  subtitle: "Both as a percentage of each year's average price. The range uses hourly prices throughout. 2026 is year to date.",
  width, height: 340, marginLeft: 60, marginBottom: 40,
  x: {type: "band", label: null},
  y: {label: "% of that year's average price", grid: true},
  color: {legend: true, domain: ["On-peak minus off-peak block", "Daily high minus low"], range: ["#CC79A7", "#0072B2"]},
  marks: [
    Plot.lineY(spreadSeries, {x: "year", y: "value", stroke: "metric", strokeWidth: 2.5, marker: "circle", tip: true}),
    Plot.ruleY([0]),
  ],
})
```

The gap between the day's highest and lowest hourly price rose from
**${pct(first.intraday_spread_pct_of_price)}** of the average price in
${first.year} to **${pct(last.intraday_spread_pct_of_price)}** in ${last.year}.
${crisis.year}, the most expensive year in the sample, sits at
${pct(crisis.intraday_spread_pct_of_price)}, no wider than ${first.year} in
relative terms. The gas crisis raised the price level; what changed afterwards
is the shape of the day.

```js
const shapeYears = [first.year, latestFull.year, last.year];
const shapeRows = shape.filter((d) => shapeYears.includes(d.year));
```

```js
Plot.plot({
  title: "Midday fell below the night; the evening became the peak",
  subtitle: "Mean price by market-local clock hour, indexed to each year's average price (100 = baseload).",
  width, height: 340, marginLeft: 60,
  x: {label: "hour, market local time", ticks: [0, 4, 8, 12, 16, 20, 23], grid: true},
  y: {label: "% of that year's average price", grid: true},
  color: {legend: true, domain: shapeYears, range: ["#999999", "#E69F00", "#0072B2"]},
  marks: [
    Plot.lineY(shapeRows, {x: "local_hour", y: "pct_of_baseload", stroke: "year", strokeWidth: 2.5, tip: true}),
    Plot.ruleY([100], {strokeDasharray: "3,3"}),
  ],
})
```

In ${first.year} the day was a plateau. It is now a trough between two peaks:
midday prices have fallen below night-time prices, and the evening ramp, when
solar has gone and demand has not, is the most expensive part of the day.

## 3. What the shape is worth to a battery

The table dispatches a 1 MW / 4 MWh battery against realised prices with perfect
foresight and one charge–discharge cycle a day, before operating, degradation
and capital costs. It is the ceiling for day-ahead arbitrage under these
assumptions, not an achievable margin. GW and GWh are Germany's installed
battery fleet that year.

```js
Inputs.table(
  foresight4.map((d) => ({
    Year: d.year === last.year ? `${d.year} (partial)` : d.year,
    "EUR/MW/d": Math.round(d.eur_per_mw_day),
    GW: d.battery_power_gw,
    GWh: d.battery_energy_gwh,
  })),
  {format: {GW: num, GWh: num}, layout: "auto", rows: 12}
)
```

${crisis.year} remains the best year in euros (EUR
${eur(foresight(crisis.year).eur_per_mw_day)}/MW/day against EUR
${eur(fleetLast.eur_per_mw_day)} in ${last.year}), because a volatile gas stack
set the price. ${last.year} reaches
**${pct((last.intraday_spread / crisis.intraday_spread) * 100)} of ${crisis.year}'s
absolute daily range at a
${pct(Math.abs(last.baseload_price / crisis.baseload_price - 1) * 100)} lower
average price**. The ${crisis.year} spread was tied to gas and faded with it; the
current one is tied to the solar profile, which is still growing. How long it
lasts depends mainly on how much flexible capacity is built to trade it.

## 4. Storage competition is not yet visible in margins

Germany's battery fleet grew from ${num(fleetFirst.battery_power_gw)} GW to
**${num(fleetLast.battery_power_gw)} GW** over the sample, while the
perfect-foresight margin per MW rose. Pumped hydro, the incumbent competitor for
the same spread, has stayed near ${num(pumpedLast.value)} GW since
${pumpedFirst.period}.

```js
Inputs.table(
  ["2022", "2023", "2024", "2025", last.year].map((period) => ({
    Year: period === last.year ? `${period} (partial)` : period,
    GW: capAt("Battery storage (power)", period).value,
    GWh: capAt("Battery storage (capacity)", period).value,
    Hours: fleetHours(period),
  })),
  {
    format: {
      GW: num,
      GWh: num,
      Hours: (v) => v.toFixed(2),
    },
    layout: "auto",
    rows: 6,
  }
)
```

This does not show that competition is absent. The provider reports the battery
fleet as one aggregate, so residential and grid-scale capacity cannot be
separated. An average duration of ${fleetHours(last.year).toFixed(2)} hours
is consistent with a fleet of mostly home systems but does not prove it, and
annual data cannot separate the fleet's effect from gas prices and weather. The
indicator to watch is duration: it rose from ${fleetHours("2024").toFixed(2)} to
${fleetHours(last.year).toFixed(2)} hours since 2024, and grid-scale 2–4 hour
batteries compete directly for the midday trough.

## 5. A forecast adds a thin margin on top of the shape

```js
const meta = await FileAttachment("data/forecast.json").json();
const run = meta.runs.find((d) => d.zone === "DE-LU");
const scores = [...await FileAttachment("data/forecast_scores.parquet").parquet()];
const overall = scores.filter((d) => d.scope === "overall");
const ridgeScore = overall.find((d) => d.model === "ridge");
const bestBaseline = overall
  .filter((d) => d.model.startsWith("naive_"))
  .sort((a, b) => a.mae - b.mae)[0];
const sens = [...await FileAttachment("data/battery_sensitivities.parquet").parquet()];
const base4 = sens.find((d) => d.strategy === "ridge" && d.energy_mwh === 4 && d.scenario === "base");
const sampleYears = base4.days / 365.25;
```

A per-hour Ridge regression, using only what is known at the 12:00 auction gate
on the day before delivery, cuts the mean absolute price error by
**${num(run.best_skill_vs_best_baseline_pct)}%** against the best naive forecast
(EUR ${num(ridgeScore.mae)} against ${num(bestBaseline.mae)}/MWh).

For the 4-hour battery, that is worth about **EUR
${eur(base4.incremental_vs_best_naive_eur_mw / sampleYears)}/MW a year** over the
best simple scheduling rule, or
${pct((base4.incremental_vs_best_naive_eur_mw / base4.profit_eur) * 100)} of the
battery's gross margin. The simple rule, which repeats the last similar day,
earns the rest by following the recurring shape, and Ridge loses to it on
${base4.underperform_days} of ${base4.days} days. In day-ahead arbitrage the
shape carries most of the value; forecasting skill pays on atypical days and in
the price tails.

[Forecast evidence](./forecast) · [Storage value](./battery)

## Risks to this view

- **Gas prices.** A cheaper marginal unit would lower the evening peak without
  lifting the midday trough.
- **Grid-scale storage.** Two- to four-hour batteries compete for exactly this
  spread; fleet duration is the first sign they are arriving.
- **Market design.** Fifteen-minute day-ahead products since October 2025, and any
  change to support payments in negative-price hours, change both the trade and
  its measurement.
- **Evidence.** The results are retrospective, on history inspected during
  development. A prospective pilot has issued forecasts before the gate for
  ${ridgeArm ? ridgeArm.issued : 0} of ${ridgeArm ? ridgeArm.days : 0} delivery
  days attempted (as of ${ledgerDate}). It will show whether the process runs
  reliably, not whether the value holds across seasons.

## Scope

- **Market:** DE-LU day-ahead auction. Prices are hourly throughout; since
  October 2025, each hour is the average of four quarter-hour prices.
- **Battery:** 1 MW with 1, 2 or 4 MWh, 90% round-trip efficiency, one
  charge–discharge cycle a day, empty at the start and end of each day. Margins
  are simulated day-ahead arbitrage under these assumptions: before operating,
  degradation and capital costs, and without intraday or balancing revenue.
- **Partial year:** ${last.year} runs to mid-September, so its figures are not
  full-year values. In complete years since 2019, the January–September daily
  range differed from the full-year figure by −4% to +11% (−36% in 2021, when the
  gas spike came in the fourth quarter).
- **Sources:** Energy-Charts (Fraunhofer ISE, CC BY 4.0), which republishes
  ENTSO-E and SMARD data. [Definitions and assumptions](./methodology).

## About me

**Pedro Cabral**

I am a power market analyst with experience covering Brazil, Chile and Argentina. My work focuses on electricity market fundamentals, price formation and the commercial implications of the energy transition.

This independent project extends my research to European power markets, examining German day-ahead prices and the value of forecasting for battery dispatch.

[Research repository](https://github.com/Pedrods20/german-power-research) · [GitHub profile](https://github.com/Pedrods20)

---

## Market context

```js
const currency = await FileAttachment("data/data_as_of.json").json();
const dailyPrices = [...await FileAttachment("data/daily_prices.parquet").parquet()];
const mix = [...await FileAttachment("data/generation_mix.parquet").parquet()];
const priceRows = dailyPrices.filter((d) => String(d.zone) === "DE-LU");
const mixRows = mix.filter((d) => String(d.zone) === "DE-LU" && d.fuel !== "imports");
const fuelColor = {coal: "#5A4632", gas: "#56B4E9", oil: "#000000", nuclear: "#CC79A7", hydro: "#0072B2", hydro_pumped_storage: "#7FB3D5", wind: "#009E73", solar: "#F0E442", biomass: "#8B6F47", geothermal: "#B15928", waste: "#999999", battery: "#E69F00", other: "#BBBBBB"};
const fuelOrder = Object.keys(fuelColor);
```

Data through **${currency.data_as_of ? currency.data_as_of.slice(0, 10) : "the latest monthly export"}**.

```js
Plot.plot({
  title: "DE-LU daily average day-ahead price",
  subtitle: "All hours. The 2021–22 gas shock is a price-level event; the shape change above is not.",
  width, height: 280, marginLeft: 55,
  x: {type: "utc", label: null}, y: {label: "EUR/MWh", grid: true},
  marks: [Plot.lineY(priceRows, {x: (d) => new Date(d.date), y: "all_hours", stroke: "#0072B2", tip: true}), Plot.ruleY([0])],
})
```

```js
Plot.plot({
  title: "DE-LU monthly generation mix",
  subtitle: "Share of generated energy; imports and storage are not counted as generation.",
  width, height: 320, marginLeft: 55,
  x: {type: "band", label: null, tickRotate: -40}, y: {label: "% of generation", grid: true, domain: [0, 100]},
  color: {domain: fuelOrder, range: fuelOrder.map((f) => fuelColor[f]), legend: true},
  marks: [Plot.barY(mixRows, {x: "month", y: "share_pct", fill: "fuel", order: fuelOrder, tip: true}), Plot.ruleY([0])],
})
```

<div class="note">Historical data is refreshed monthly. Missing observations remain missing; the charts never turn a provider gap into zero.</div>

<style>
.note {
  border-left: 3px solid var(--theme-foreground-focus);
  padding: .5rem 0 .5rem 1rem;
  color: var(--theme-foreground-muted);
}
</style>
