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
const monthlyMargins = [...await FileAttachment("data/battery_monthly.parquet").parquet()];
const attributionRows = [...await FileAttachment("data/battery_attribution.parquet").parquet()];
const revenueStack = [...await FileAttachment("data/revenue_stack.parquet").parquet()];
const quarterHours = [...await FileAttachment("data/quarter_hour_value.parquet").parquet()];
const capacity = [...await FileAttachment("data/capacity.parquet").parquet()];
const ledgerStatus = await FileAttachment("data/ledger_status.json").json();
const ridgeArm = ledgerStatus.arms.find((d) => d.model === "ridge");
const ledgerDate = ledgerStatus.as_of ? ledgerStatus.as_of.slice(0, 10) : "this build";
const yearlyCap = capacity.filter((d) => d.time_step === "yearly" && !d.is_planned);
const capAt = (technology, period) => yearlyCap.find((d) => d.technology === technology && String(d.period) === period);
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
const foresight = (period) => foresight4.find((d) => d.year === period);
const eur = (v) => v.toLocaleString("en", {maximumFractionDigits: 0});
const num = (v) => v.toFixed(1);
const pct = (v) => `${v.toFixed(0)}%`;
const share = (v) => pct(100 * v);
const rate = (v) => v.toFixed(2);
```

```js
const capture = d3.groups(monthlyMargins.filter((d) => d.energy_mwh === 4), (d) => String(d.month).slice(0, 4))
  .map(([year, rows]) => {
    const total = (strategy) => d3.sum(rows.filter((d) => d.strategy === strategy), (d) => d.profit_eur);
    return {year, perfect: total("perfect_foresight"), naive: total("naive_similar_day"), ridge: total("ridge")};
  })
  .sort((a, b) => a.year.localeCompare(b.year));
const captureRows = capture.flatMap((d) => [
  {year: d.year, strategy: "Repeat the last similar day", value: 100 * d.naive / d.perfect},
  {year: d.year, strategy: "Ridge forecast", value: 100 * d.ridge / d.perfect},
]);
const captureFirst = capture[0];
const captureLast = capture[capture.length - 1];
const surprise = attributionRows.filter((d) => d.energy_mwh === 4 && d.dimension === "shape_surprise");
const typicalDays = surprise.filter((d) => d.bucket.startsWith("1") || d.bucket.startsWith("2"));
const atypical = surprise.find((d) => d.bucket.startsWith("5"));
const stack = (year, market) => revenueStack.find((d) => d.energy_mwh === 4 && d.year === year && d.market === market);
const stackLast = d3.max(revenueStack.filter((d) => d.year !== "all"), (d) => d.year);
const closing = (year) => stack(year, "day_ahead").eur_per_mw_day / stack(year, "afrr").eur_per_mw_day;
const quarterUplift = (energy) => {
  const at = (resolution) => quarterHours.find((d) => d.energy_mwh === energy && d.strategy === "perfect_foresight" && d.resolution === resolution);
  return at("quarter_hour").eur_per_mw_day / at("hourly").eur_per_mw_day - 1;
};
const fleetGw = capAt("Battery storage (power)", last.year).value;
const run = (await FileAttachment("data/forecast.json").json()).runs.find((d) => d.zone === "DE-LU");
const sens = [...await FileAttachment("data/battery_sensitivities.parquet").parquet()];
const base4 = sens.find((d) => d.strategy === "ridge" && d.energy_mwh === 4 && d.scenario === "base");
```

In German day-ahead arbitrage, the recurring solar-driven price shape carries
most of the value, and a price forecast earns on the days that shape breaks. This
note measures the shape in Germany–Luxembourg (DE-LU) prices, values it for a
battery against simple rules and the balancing markets, and tests what a
forecast made at the auction gate adds.

**4-hour battery:** a rule that repeats the last similar day captured
**${pct(100 * captureFirst.naive / captureFirst.perfect)} → ${pct(100 * captureLast.naive / captureLast.perfect)}**
of the perfect-foresight margin (${captureFirst.year} → ${captureLast.year} YTD) ·
**${share(atypical.incremental_share)}** of the forecast's gain comes from the most
atypical fifth of days · day-ahead arbitrage earned
**${share(closing("2021"))} → ${share(closing(stackLast))}** of what aFRR capacity paid
(2021 → ${stackLast})

**Price shape, ${first.year} → ${last.year} YTD:** on-peak premium **EUR
${num(first.spread)} → ${num(last.spread)}/MWh** · daily price range
**${pct(first.intraday_spread_pct_of_price)} → ${pct(last.intraday_spread_pct_of_price)}**
of the average price · solar capture rate **${rate(first.solar_capture_rate)} →
${rate(last.solar_capture_rate)}** · negative-price hours **${num(first.negative_pct)}%
→ ${num(last.negative_pct)}%**

[Forecast evidence](./forecast) · [Storage value](./battery) · [Methodology](./methodology)

## 1. The shape carries most of the value

```js
Plot.plot({
  title: "A rule that repeats the shape now takes over 90% of the ceiling",
  subtitle: "Share of the perfect-foresight day-ahead margin captured, 1 MW / 4 MWh battery, one cycle a day. 2020 starts on 3 January; the last year is year to date.",
  width, height: 280, marginLeft: 50,
  x: {type: "band", label: null},
  y: {label: "% of perfect foresight", grid: true, domain: [70, 100]},
  color: {legend: true, domain: ["Repeat the last similar day", "Ridge forecast"], range: ["#009E73", "#0072B2"]},
  marks: [Plot.lineY(captureRows, {x: "year", y: "value", stroke: "strategy", strokeWidth: 2.5, marker: "circle", tip: true})],
})
```

A 1 MW / 4 MWh battery dispatched once a day can, with perfect foresight, earn
EUR ${eur(foresight(captureLast.year).eur_per_mw_day)}/MW a day in
${captureLast.year}. A rule that simply repeats the last similar day's prices
captured ${pct(100 * captureFirst.naive / captureFirst.perfect)} of that in
${captureFirst.year} and **${pct(100 * captureLast.naive / captureLast.perfect)}**
in ${captureLast.year}. The forecast sits a few points above it every year. The
more regular the solar-driven shape becomes, the less room is left for a
forecast.

## 2. The forecast earns when the shape breaks

A per-hour Ridge regression, using only what is known at the 12:00 auction gate
on the day before delivery, cuts the mean absolute price error by
${num(run.best_skill_vs_best_baseline_pct)}% against the best naive forecast and
picks the day's cheapest and dearest hours more often. For the 4-hour battery that
is worth about EUR ${eur(base4.incremental_vs_best_naive_eur_mw / (base4.days / 365.25))}/MW
a year over the simple rule, ${share(base4.incremental_vs_best_naive_eur_mw / base4.profit_eur)}
of the battery's gross margin.

Where it earns matters more than how much. On the
${share(d3.sum(typicalDays, (d) => d.day_share))} of days whose shape was most
typical, Ridge **loses** to the simple rule; the most atypical fifth of days
carries **${share(atypical.incremental_share)}** of its gain. Negative-price days
are not where it earns. The desk reading is a switch: follow the recurring
shape, and act on the forecast only when it disagrees strongly with it. This
study has not yet tested that rule.

[Forecast evidence](./forecast) · [Storage value](./battery)

## 3. Why the shape exists

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
  width, height: 320, marginLeft: 60, marginBottom: 40,
  x: {type: "band", label: null},
  y: {label: "% of that year's average price", grid: true},
  color: {legend: true, domain: ["On-peak minus off-peak block", "Daily high minus low"], range: ["#CC79A7", "#0072B2"]},
  marks: [
    Plot.lineY(spreadSeries, {x: "year", y: "value", stroke: "metric", strokeWidth: 2.5, marker: "circle", tip: true}),
    Plot.ruleY([0]),
  ],
})
```

Installed solar rose from ${num(first.solar_capacity_gw)} to
${num(last.solar_capacity_gw)} GW over the sample, and the price solar plants earn
fell from ${rate(first.solar_capture_rate)} to ${rate(last.solar_capture_rate)} of
the average price; wind's barely moved. The on-peak block (08:00–20:00 on
weekdays) went from a EUR ${num(first.spread)}/MWh premium to a
${num(Math.abs(last.spread))} discount, while the gap between the day's highest
and lowest hourly price rose from ${pct(first.intraday_spread_pct_of_price)} to
**${pct(last.intraday_spread_pct_of_price)}** of the average price.
${crisis.year}, the most expensive year, sits at
${pct(crisis.intraday_spread_pct_of_price)}: the gas crisis raised the price
level, and what changed afterwards is the shape.

```js
const shapeYears = [first.year, latestFull.year, last.year];
const shapeRows = shape.filter((d) => shapeYears.includes(d.year));
```

```js
Plot.plot({
  title: "Midday fell below the night; the evening became the peak",
  subtitle: "Mean price by market-local clock hour, indexed to each year's average price (100 = baseload).",
  width, height: 320, marginLeft: 60,
  x: {label: "hour, market local time", ticks: [0, 4, 8, 12, 16, 20, 23], grid: true},
  y: {label: "% of that year's average price", grid: true},
  color: {legend: true, domain: shapeYears, range: ["#999999", "#E69F00", "#0072B2"]},
  marks: [
    Plot.lineY(shapeRows, {x: "local_hour", y: "pct_of_baseload", stroke: "year", strokeWidth: 2.5, tip: true}),
    Plot.ruleY([100], {strokeDasharray: "3,3"}),
  ],
})
```

The day turned from a plateau into a trough between two peaks, and the trough
arrives at the same hours on every sunny day. That regularity is why a simple
rule captures so much: ${crisis.year} still paid the most in euros (EUR
${eur(foresight(crisis.year).eur_per_mw_day)}/MW a day with perfect foresight,
against ${eur(foresight(last.year).eur_per_mw_day)} in ${last.year}), but its
spread came from gas and left with it, while today's comes from the solar
profile, which is still growing.

## 4. Beyond the day-ahead hour

Quarter-hour products, traded since October 2025, raise the day-ahead arbitrage
ceiling by ${share(quarterUplift(1))} for a 1-hour battery and
${share(quarterUplift(4))} for a 4-hour one: worth having, but far less than the
16% by which they widen the daily price range. Balancing capacity has paid more
than arbitrage. Since November 2020, aFRR up and down averaged EUR
${eur(stack("all", "afrr").eur_per_mw_day)}/MW a day and FCR
${eur(stack("all", "fcr").eur_per_mw_day)}, against
${eur(stack("all", "day_ahead").eur_per_mw_day)} for day-ahead arbitrage with the
forecast. Those markets are shallow, though: Germany procures about 0.6 GW of FCR
and 2 GW of aFRR each way, against ${num(fleetGw)} GW of installed batteries. And
the gap is closing: for a 4-hour battery, arbitrage earned
${share(closing("2021"))} of the aFRR capacity value in 2021 and
${share(closing(stackLast))} in ${stackLast}.

[Storage value](./battery)

## Risks to this view

- **Gas prices.** A cheaper marginal unit would lower the evening peak without
  lifting the midday trough.
- **Grid-scale storage.** Two- to four-hour batteries compete for exactly this
  spread. The fleet's average duration, ${fleetHours(last.year).toFixed(2)} hours in
  ${last.year}, is the first sign of them arriving; the small balancing markets
  would fill first.
- **Market design.** Fifteen-minute products, and any change to support payments
  in negative-price hours, change both the trade and its measurement.
- **Evidence.** The results are retrospective, on history inspected during
  development. A prospective pilot has issued forecasts before the gate for
  ${ridgeArm ? ridgeArm.issued : 0} of ${ridgeArm ? ridgeArm.days : 0} delivery
  days attempted (as of ${ledgerDate}). It will show whether the process runs
  reliably, not whether the value holds across seasons.

## Scope

- **Markets:** the DE-LU day-ahead auction, with hourly prices except in the
  quarter-hour study, and German FCR and aFRR capacity auctions. Continuous
  intraday trading is not modelled, for want of a free public price source; it
  is the natural next step.
- **Battery:** 1 MW with 1, 2 or 4 MWh, 90% round-trip efficiency, one
  charge–discharge cycle a day, empty at the start and end of each day. Margins
  are simulated under these assumptions: before operating, degradation and
  capital costs, and not a revenue estimate for a real asset.
- **Partial year:** ${last.year} runs to mid-September, so its figures are not
  full-year values. In complete years since 2019, the January–September daily
  range differed from the full-year figure by −4% to +11% (−36% in 2021, when the
  gas spike came in the fourth quarter).
- **Sources:** Energy-Charts (Fraunhofer ISE, CC BY 4.0), which republishes
  ENTSO-E and SMARD data, and regelleistung.net, the German TSOs' balancing
  platform. [Definitions and assumptions](./methodology).

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
