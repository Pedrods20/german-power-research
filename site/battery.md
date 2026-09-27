---
title: Storage value
---

# Battery dispatch: margins and forecast value

A 1 MW battery is scheduled each day from a forecast made at the 12:00 D-1 gate
and settled against realised DE-LU day-ahead prices. The same battery is also run
on three simple rules that need no model. The difference between them is what
the forecast is worth.

```js
const summary = [...await FileAttachment("data/battery_summary.parquet").parquet()];
const monthlyMargins = [...await FileAttachment("data/battery_monthly.parquet").parquet()];
const dispatchExample = [...await FileAttachment("data/battery_dispatch_example.parquet").parquet()];
const risk = [...await FileAttachment("data/battery_risk.parquet").parquet()];
const comparisons = [...await FileAttachment("data/battery_comparisons.parquet").parquet()];
const costs = [...await FileAttachment("data/battery_costs.parquet").parquet()];
const stresses = [...await FileAttachment("data/battery_sensitivities.parquet").parquet()];
const coverage = [...await FileAttachment("data/battery_coverage.parquet").parquet()];
const cannibalisation = [...await FileAttachment("data/cannibalisation.parquet").parquet()];
const capacityYearly = [...await FileAttachment("data/capacity_price_yearly.parquet").parquet()];
const capacityCorrelation = [...await FileAttachment("data/capacity_price_correlation.parquet").parquet()];
const extrapolationFlags = [...await FileAttachment("data/capacity_extrapolation_flags.parquet").parquet()];
const competitionCorrelation = [...await FileAttachment("data/battery_competition_correlation.parquet").parquet()];
const attributionRows = [...await FileAttachment("data/battery_attribution.parquet").parquet()];
const quarterHours = [...await FileAttachment("data/quarter_hour_value.parquet").parquet()];
const revenueStack = [...await FileAttachment("data/revenue_stack.parquet").parquet()];
const gw = (value) => value == null ? "n/a" : value.toFixed(1);
const labels = new Map([
  ["ridge", "Ridge"], ["lightgbm", "LightGBM"],
  ["naive_previous_day", "Previous day"], ["naive_previous_week", "Previous week"],
  ["naive_similar_day", "Similar day"], ["perfect_foresight", "Perfect foresight"],
  ["no_trade", "No trade"],
]);
const scenarioNames = new Map([
  ["base", "Base: 90% efficiency, zero costs"],
  ["cost_2_3", "Costs: 2 / 3 EUR per grid MWh"],
  ["cost_5_10", "Costs: 5 / 10 EUR per grid MWh"],
  ["efficiency_85", "85% round-trip efficiency"],
  ["signal_50", "50% forecast deviation from D-1"],
  ["calendar_downtime", "One unavailable day in twenty"],
  ["two_episodes", "Two charge/discharge episodes a day"],
  ["two_episodes_cost_2_3", "Two episodes + 2 / 3 EUR costs"],
  ["combined", "2/3 costs + 85% + 50% signal + downtime"],
]);
const name = (value) => labels.get(value) ?? value;
const euro = (value) => value == null ? "n/a" : value.toLocaleString("en", {maximumFractionDigits: 0});
const pct = (value) => value == null ? "n/a" : `${(100 * value).toFixed(1)}%`;
const renderTable = (id, rows, format = {}) => {
  const table = Inputs.table(rows, {format, rows: rows.length, layout: "auto"});
  table.id = id;
  return table;
};
```

```js
const duration = view(Inputs.select([1, 2, 4], {label: "Battery duration at 1 MW (hours)", value: 4}));
```

```js
const asset = (row) => row.energy_mwh === duration;
const fitted = (row) => ["ridge", "lightgbm"].includes(row.strategy);
const headline = stresses.find((d) => asset(d) && d.strategy === "ridge" && d.scenario === "base");
const batteryDays = headline.days;
const sampleYears = batteryDays / 365.25;
const twoEpisodes = stresses.find((d) => asset(d) && d.strategy === "ridge" && d.scenario === "two_episodes");
const selectedRisk = risk.filter((d) => asset(d) && fitted(d));
const selectedPairs = comparisons.filter((d) => asset(d) && fitted(d));
const baselineValue = summary.find((d) => asset(d) && d.strategy === headline.best_naive).profit_eur;
const monthly = monthlyMargins.filter(asset).map((d) => ({strategy: d.strategy, month: String(d.month), profit: d.profit_eur}));
const cumulative = d3.groups(monthly, (d) => d.strategy).flatMap(([strategy, values]) => {
  let total = 0;
  return values.sort((a, b) => a.month.localeCompare(b.month)).map((d) => ({...d, total: total += d.profit}));
});
const sample = dispatchExample.filter((d) => asset(d) && d.strategy === "ridge");
const sampleDate = d3.max(sample, (d) => String(d.local_date));
```

## Result

For the ${duration}-hour battery, Ridge earns **EUR
${euro(headline.incremental_vs_best_naive_eur_mw / sampleYears)}/MW a year** more
than the best simple rule, **${name(headline.best_naive)}**: EUR
${euro(headline.mean_daily_incremental_eur_mw)}/MW on an average day, or
${pct(headline.incremental_vs_best_naive_eur_mw / baselineValue)} more margin. The
paired 95% interval is EUR ${euro(headline.ci_low_eur_mw / sampleYears)}–${euro(headline.ci_high_eur_mw / sampleYears)}/MW
a year. The sample covers **${batteryDays} days**, ${headline.sample_start} to
${headline.sample_end}; the annual figures are averages over it, not
projections.

Most of the margin does not need a forecast. Repeating the daily shape earns the
bulk of it, and the forecast adds a thin layer on days when the shape changes.
The best simple rule is ranked over the whole sample, in hindsight; all three are
shown.

These are **simulated day-ahead arbitrage margins under the stated
assumptions**, not a revenue estimate for a real battery. They exclude operating,
degradation and capital costs, which lower returns, and intraday and balancing
revenue, which a real battery would add.

```js
renderTable("battery-scoreboard", summary.filter(asset).map((d) => ({
  Strategy: name(d.strategy), Days: d.days,
  "Operating margin (EUR/MW)": d.profit_eur / d.power_mw,
  "Equivalent cycles": d.equivalent_cycles,
  "Capture vs perfect": d.capture_vs_perfect,
})), {"Operating margin (EUR/MW)": euro, "Equivalent cycles": euro, "Capture vs perfect": pct})
```

```js
const cumulativeChart = Plot.plot({
  title: "Every strategy earns most of the margin; the gaps open slowly",
  subtitle: `Cumulative operating margin, ${duration}h battery, zero-cost base case. Partial months contain only eligible days.`,
  width, height: 320, marginLeft: 70,
  x: {type: "utc", label: null}, y: {label: "EUR per MW", grid: true},
  color: {domain: [...labels.values()], legend: true},
  marks: [
    Plot.lineY(cumulative, {x: (d) => new Date(`${d.month}-01T00:00:00Z`), y: "total", z: "strategy", stroke: (d) => name(d.strategy), tip: true}),
    Plot.ruleY([0]),
  ],
});
cumulativeChart.id = "battery-cumulative";
display(cumulativeChart);
```

```js
renderTable("battery-comparisons", selectedPairs.map((d) => ({
  Model: name(d.strategy), Comparator: name(d.baseline),
  "Increment (EUR/MW)": d.incremental_eur_mw,
  "95% low": d.ci_low_eur_mw, "95% high": d.ci_high_eur_mw,
})), {"Increment (EUR/MW)": euro, "95% low": euro, "95% high": euro})
```

Increments in this table are totals over the whole sample, not annual figures.

## The forecast's share is shrinking

```js
const byYear = d3.groups(monthlyMargins.filter(asset), (d) => String(d.month).slice(0, 4)).map(([year, rows]) => {
  const perDay = (strategy) => {
    const picked = rows.filter((d) => d.strategy === strategy);
    return d3.sum(picked, (d) => d.profit_eur / d.power_mw) / d3.sum(picked, (d) => d.days);
  };
  const ridgeDay = perDay("ridge"), naiveDay = perDay(headline.best_naive), perfectDay = perDay("perfect_foresight");
  return {year, days: d3.sum(rows.filter((d) => d.strategy === "ridge"), (d) => d.days), ridgeDay, naiveDay, uplift: ridgeDay / naiveDay - 1, naiveCapture: naiveDay / perfectDay};
}).sort((a, b) => a.year.localeCompare(b.year));
const firstYear = byYear[0];
const lastYear = byYear[byYear.length - 1];
const year2023 = byYear.find((d) => d.year === "2023");
```

```js
renderTable("battery-by-year", byYear.map((d) => ({
  Year: d.year === lastYear.year ? `${d.year} (partial)` : d.year,
  Days: d.days,
  "Ridge (EUR/MW/d)": d.ridgeDay,
  [`${name(headline.best_naive)} (EUR/MW/d)`]: d.naiveDay,
  "Increment (EUR/MW/d)": d.ridgeDay - d.naiveDay,
  "Uplift": d.uplift,
  [`${name(headline.best_naive)} vs perfect`]: d.naiveCapture,
})), {"Ridge (EUR/MW/d)": euro, [`${name(headline.best_naive)} (EUR/MW/d)`]: euro, "Increment (EUR/MW/d)": (v) => v.toFixed(1), "Uplift": pct, [`${name(headline.best_naive)} vs perfect`]: pct})
```

The simple rule's share of the perfect-foresight margin rose from
**${pct(firstYear.naiveCapture)}** in ${firstYear.year} to
**${pct(lastYear.naiveCapture)}** in ${lastYear.year}. Ridge's increment in euros
has been broadly stable since 2023, but relative to the simple rule it fell from
${pct(year2023.uplift)} to ${pct(lastYear.uplift)}. The more regular the
solar-driven shape, the more a rule that repeats it captures on its own.

## Where the forecast earns

```js
const byGroup = (dimension) => attributionRows.filter((d) => asset(d) && d.dimension === dimension).sort((a, b) => a.bucket.localeCompare(b.bucket));
const surprise = byGroup("shape_surprise");
const typical = surprise.filter((d) => d.bucket.startsWith("1") || d.bucket.startsWith("2"));
const atypical = surprise.find((d) => d.bucket.startsWith("5"));
const negativeDays = byGroup("negative_prices");
const withNegative = negativeDays.find((d) => d.bucket === "Some negative hours");
const withoutNegative = negativeDays.find((d) => d.bucket === "No negative hours");
```

```js
Plot.plot({
  title: "The forecast earns on the days the simple rule misreads",
  subtitle: `Ridge's margin over ${name(headline.best_naive)}, EUR/MW per day, by how far each day's price shape departed from the ${name(headline.best_naive)} forecast (quintiles, judged after the fact). ${duration}h battery.`,
  width, height: 260, marginLeft: 60, marginBottom: 40,
  x: {label: null, domain: surprise.map((d) => d.bucket)},
  y: {label: "EUR/MW per day", grid: true},
  marks: [
    Plot.barY(surprise, {x: "bucket", y: "mean_daily_incremental_eur_mw", fill: (d) => d.mean_daily_incremental_eur_mw < 0 ? "#D55E00" : "#0072B2", tip: true}),
    Plot.ruleY([0]),
  ],
})
```

On the ${pct(d3.sum(typical, (d) => d.day_share))} of days whose shape was most
typical, Ridge **loses** to the simple rule, by EUR
${euro(-d3.sum(typical, (d) => d.incremental_eur_mw) / d3.sum(typical, (d) => d.days))}/MW a
day. The ${pct(atypical.day_share)} most atypical days carry
**${pct(atypical.incremental_share)}** of its total gain. Negative-price days are
not where it earns: EUR ${euro(withNegative.mean_daily_incremental_eur_mw)}/MW a day
there, against ${euro(withoutNegative.mean_daily_incremental_eur_mw)} on other days,
in line with its weak negative-price calls on the [forecast page](./forecast).
This suggests a switch a desk could test: follow the recurring shape, and act on
the forecast only when it disagrees strongly with that shape. This study has not
tested that rule.

## How a forecast becomes a decision

```js
const dayProfit = (strategy) => d3.sum(dispatchExample.filter((d) => asset(d) && d.strategy === strategy && String(d.local_date) === sampleDate), (d) => d.profit_eur);
```

On ${sampleDate}, the latest day in the sample, the whole day's schedule is set
from Ridge's forecast at the gate and then settled at the prices that cleared.
Ridge earned **EUR ${euro(dayProfit("ridge"))}**, the ${name(headline.best_naive)}
rule EUR ${euro(dayProfit(headline.best_naive))}, and perfect foresight EUR
${euro(dayProfit("perfect_foresight"))}.
${dayProfit("ridge") < dayProfit(headline.best_naive) ? "It is one of the days on which the forecast cost money against the simple rule." : "On this day the forecast earned more than the simple rule."}

```js
Plot.plot({
  title: `${duration}h battery on ${sampleDate}: Ridge forecast against realised price`,
  width, height: 200, marginLeft: 65,
  x: {label: null, axis: null}, y: {label: "EUR/MWh", grid: true},
  color: {domain: ["Realised price", "Ridge forecast"], range: ["#333333", "#0072B2"], legend: true},
  marks: [
    Plot.lineY(sample, {x: "local_hour", y: "actual", stroke: () => "Realised price", tip: true}),
    Plot.lineY(sample, {x: "local_hour", y: "forecast", stroke: () => "Ridge forecast", strokeDasharray: "4,3", tip: true}),
    Plot.ruleY([0]),
  ],
})
```

```js
Plot.plot({
  title: "The schedule it produced",
  subtitle: "Negative bars charge the battery, positive bars discharge it; the line is the state of charge.",
  width, height: 200, marginLeft: 65,
  x: {label: "Market-local hour"}, y: {label: "MWh", grid: true},
  color: {domain: ["State of charge", "Action"], range: ["#0072B2", "#D55E00"], legend: true},
  marks: [
    Plot.lineY(sample, {x: "local_hour", y: "soc_mwh", stroke: () => "State of charge", tip: true}),
    Plot.barY(sample, {x: "local_hour", y: "action_mwh", fill: () => "Action", fillOpacity: .55, tip: true}),
    Plot.ruleY([0]),
  ],
})
```

## What 15-minute products are worth

```js
const qh = (strategy, resolution) => quarterHours.find((d) => d.energy_mwh === duration && d.strategy === strategy && d.resolution === resolution);
const qhRows = ["perfect_foresight", "naive_previous_day"].map((strategy) => ({strategy, hourly: qh(strategy, "hourly"), quarter: qh(strategy, "quarter_hour")}));
const qhUplift = (row) => row.quarter.eur_per_mw_day / row.hourly.eur_per_mw_day - 1;
const qhOneHour = quarterHours.filter((d) => d.energy_mwh === 1);
const qhFourHours = quarterHours.filter((d) => d.energy_mwh === 4);
const upliftAt = (rows, strategy) => rows.find((d) => d.strategy === strategy && d.resolution === "quarter_hour").eur_per_mw_day / rows.find((d) => d.strategy === strategy && d.resolution === "hourly").eur_per_mw_day - 1;
```

```js
renderTable("battery-quarter-hours", qhRows.map((row) => ({
  Strategy: row.strategy === "naive_previous_day" ? "Repeat the previous day" : name(row.strategy),
  "Hourly (EUR/MW/d)": row.hourly.eur_per_mw_day,
  "Quarter-hour (EUR/MW/d)": row.quarter.eur_per_mw_day,
  Uplift: qhUplift(row),
})), {"Hourly (EUR/MW/d)": euro, "Quarter-hour (EUR/MW/d)": euro, Uplift: pct})
```

Since October 2025 the auction clears quarter-hours. On the same
${qhRows[0].quarter.days} days (${qhRows[0].quarter.sample_start} to
${qhRows[0].quarter.sample_end}), trading quarter-hours instead of hours raises
the perfect-foresight margin by ${pct(upliftAt(qhOneHour, "perfect_foresight"))} for
a 1-hour battery and ${pct(upliftAt(qhFourHours, "perfect_foresight"))} for a 4-hour
one. Quarter-hour extremes widen the daily price range by about 16%, but a
battery that moves energy over several hours captures only part of that: the
shorter the battery, the more the finer products are worth. A rule that repeats
the previous day's quarter-hours keeps most of the gain. The forecast on this site
is still hourly, so none of this value is in its results.

## Day-ahead is one market among several

```js
const marketNames = new Map([
  ["day_ahead", "Day-ahead arbitrage (Ridge)"],
  ["day_ahead_perfect", "Day-ahead, perfect foresight"],
  ["fcr", "FCR capacity"],
  ["afrr", "aFRR capacity, up and down"],
  ["ex_ante_rule", "Ex-ante daily choice"],
  ["hindsight_best", "Best market in hindsight"],
]);
const stack = revenueStack.filter((d) => d.energy_mwh === duration);
const stackYears = stack.filter((d) => d.year !== "all" && ["day_ahead", "fcr", "afrr"].includes(d.market));
const stackAt = (year, market) => stack.find((d) => d.year === year && d.market === market);
const stackTotal = (market) => stackAt("all", market);
const stackLast = d3.max(stackYears, (d) => d.year);
const closing = (year) => stackAt(year, "day_ahead").eur_per_mw_day / stackAt(year, "afrr").eur_per_mw_day;
```

```js
Plot.plot({
  title: "Balancing paid more per MW; day-ahead arbitrage is closing the gap",
  subtitle: `EUR per MW per day, ${duration}h battery. Balancing is capacity revenue only; 2020 starts in November and ${stackLast} is year to date.`,
  width, height: 300, marginLeft: 60,
  x: {type: "band", label: null},
  y: {label: "EUR/MW per day", grid: true},
  color: {legend: true, domain: ["aFRR capacity, up and down", "FCR capacity", "Day-ahead arbitrage (Ridge)"], range: ["#009E73", "#CC79A7", "#0072B2"]},
  marks: [
    Plot.lineY(stackYears, {x: "year", y: "eur_per_mw_day", stroke: (d) => marketNames.get(d.market), strokeWidth: 2.5, marker: "circle", tip: true}),
    Plot.ruleY([0]),
  ],
})
```

```js
renderTable("battery-revenue-stack", [...marketNames.keys()].map((market) => stackTotal(market)).map((d) => ({
  Market: marketNames.get(d.market),
  "EUR/MW per day": d.eur_per_mw_day,
  "Days the rule chose it": d.rule_days,
})), {"EUR/MW per day": euro, "Days the rule chose it": (v) => v == null ? "" : euro(v)})
```

Over the ${stackTotal("afrr").days.toLocaleString("en")} days from November 2020
with both markets published, aFRR capacity paid **EUR
${euro(stackTotal("afrr").eur_per_mw_day)}/MW a day** and FCR
${euro(stackTotal("fcr").eur_per_mw_day)}, against
${euro(stackTotal("day_ahead").eur_per_mw_day)} for day-ahead arbitrage with the Ridge
forecast. A rule that picks each day's market on what is known before the
balancing auctions close chose aFRR on
${pct(stackTotal("afrr").rule_days / stackTotal("afrr").days)} of days and earned
${euro(stackTotal("ex_ante_rule").eur_per_mw_day)}, close to the best market in
hindsight.

Two things temper that. The balancing markets are shallow: Germany procures about
0.6 GW of FCR and about 2 GW of aFRR each way, against 21 GW of installed
batteries, so they cannot absorb the fleet. And these are capacity payments,
before the prequalification, energy management and bidding risk they require;
aFRR is pay-as-bid, so its average accepted price is not guaranteed to any bid.
Meanwhile the gap is closing: for a ${duration}-hour battery, day-ahead arbitrage
earned **${pct(closing("2021"))}** of the aFRR capacity value in 2021 and
**${pct(closing(stackLast))}** in ${stackLast}. Intraday trading, activation
energy and mFRR are not modelled.

## Costs and robustness

The stresses below rerun the optimiser for Ridge without retuning it. Costs apply
to grid-side charging plus discharging MWh; the rates are illustrative, not
calibrated German project costs.

```js
renderTable("battery-costs", costs.filter((d) => asset(d) && fitted(d)).map((d) => ({
  Model: name(d.strategy),
  "Variable / degradation": `${d.variable_cost_eur_mwh} / ${d.degradation_cost_eur_mwh}`,
  "Gross margin (EUR)": d.gross_revenue_eur,
  "Stated costs (EUR)": d.operating_cost_eur + d.degradation_cost_eur,
  "After-cost margin (EUR)": d.profit_eur,
  "Best naive": name(d.best_naive),
  "Increment (EUR/MW)": d.incremental_vs_best_naive_eur_mw,
})), {"Gross margin (EUR)": euro, "Stated costs (EUR)": euro, "After-cost margin (EUR)": euro, "Increment (EUR/MW)": euro})
```

```js
renderTable("battery-sensitivities", stresses.filter((d) => asset(d) && d.strategy === "ridge").sort((a, b) => [...scenarioNames.keys()].indexOf(a.scenario) - [...scenarioNames.keys()].indexOf(b.scenario)).map((d) => ({
  Scenario: scenarioNames.get(d.scenario),
  "Available days": d.available_days,
  "Margin (EUR/MW)": d.profit_eur_mw,
  "Best naive": name(d.best_naive),
  "Increment (EUR/MW)": d.incremental_vs_best_naive_eur_mw,
  "95% low": d.ci_low_eur_mw, "95% high": d.ci_high_eur_mw,
})), {"Margin (EUR/MW)": euro, "Increment (EUR/MW)": euro, "95% low": euro, "95% high": euro})
```

```js
html`<a href=${await FileAttachment("data/battery_sensitivities.parquet").url()} download="battery_sensitivities.parquet">Download all sensitivity results (Parquet)</a>`
```

**A second daily cycle adds margin, not forecast value.** Allowing two
charge–discharge episodes a day raises gross margin by
**${pct(twoEpisodes.profit_eur / headline.profit_eur - 1)}**, at
${(twoEpisodes.equivalent_cycles / twoEpisodes.days).toFixed(2)} equivalent
cycles a day, while Ridge's advantage over the best simple rule moves from EUR
${euro(headline.incremental_vs_best_naive_eur_mw / sampleYears)} to EUR
${euro(twoEpisodes.incremental_vs_best_naive_eur_mw / sampleYears)}/MW a year:
the simple rule earns almost all of the extra margin too. The second cycle
trades the midday solar trough, the most predictable feature of the German day.

<details>
<summary>Scenario definitions</summary>

- **85% efficiency** follows the [NREL ATB 2024](https://atb.nrel.gov/electricity/2024/utility-scale_battery_storage)
  technical reference. ATB treats augmentation within fixed O&M rather than
  per-MWh charges, so it does not validate the illustrative cost rates; do not
  combine both approaches without checking for double counting.
- **50% signal** halves each fitted forecast's deviation from the previous-day
  forecast, without using realised prices. It tests how much the result depends
  on the forecast signal; it is not a calibrated error distribution.
- **Downtime** removes one whole day in every twenty, anchored at 1 January 2025
  and shared by all strategies. The outage is assumed known before scheduling.
- **Combined** applies the 2/3 EUR costs, 85% efficiency, 50% signal and the
  downtime calendar together.

</details>

## Downside and concentration

```js
renderTable("battery-risk", selectedRisk.map((d) => ({
  Model: name(d.strategy),
  "Loss days": d.loss_days, "Worst day (EUR)": d.worst_day_eur,
  "Max drawdown (EUR)": d.max_drawdown_eur,
  "Top 5 days / positive margin": d.top_5_days_share_positive_margin,
})), {"Worst day (EUR)": euro, "Max drawdown (EUR)": euro, "Top 5 days / positive margin": pct})
```

Ridge underperforms the best simple rule on **${headline.underperform_days} of
${batteryDays} days**. Its five best days account for
${pct(headline.top_5_days_share_positive_incremental)} of all positive
incremental margin, and removing them still leaves EUR
${euro(headline.incremental_without_best_5_days_eur_mw)}/MW, so the advantage is
not driven by a handful of days.

<details>
<summary>How the intervals are built</summary>

Intervals use 2,000 paired resamples of non-overlapping seven-day blocks (seed
20260914); missing dates are not compressed. They do not account for model
selection, multiple comparisons, structural change or omitted costs.

</details>

## Duration

```js
renderTable("battery-durations", stresses.filter((d) => d.strategy === "ridge" && d.scenario === "base").sort((a, b) => a.energy_mwh - b.energy_mwh).map((d) => ({
  "Duration (h)": d.energy_mwh / d.power_mw,
  "Margin (EUR/MW)": d.profit_eur_mw,
  "Best naive": name(d.best_naive),
  "Increment (EUR/MW)": d.incremental_vs_best_naive_eur_mw,
  "Increment / MWh capacity": d.incremental_vs_best_naive_eur_mw * d.power_mw / d.energy_mwh,
})), {"Margin (EUR/MW)": euro, "Increment (EUR/MW)": euro, "Increment / MWh capacity": euro})
```

Longer duration earns more per MW but needs more energy capacity, so compare the
increment per MWh as well. Ranking durations as investments would need capital
costs, availability terms, lifetime degradation and other revenues, which are
outside this study.

## Is this margin durable as the market changes?

```js
const solarCannibal = cannibalisation.filter((d) => d.fuel === "solar").sort((a, b) => a.period.localeCompare(b.period));
const windCannibal = cannibalisation.filter((d) => d.fuel === "wind").sort((a, b) => a.period.localeCompare(b.period));
const firstSolar = solarCannibal[0];
const lastSolar = solarCannibal[solarCannibal.length - 1];
const lastWind = windCannibal[windCannibal.length - 1];
const yearlyByYear = new Map(capacityYearly.map((d) => [d.year, d]));
const firstSolarYear = yearlyByYear.get(firstSolar.period);
const lastSolarYear = yearlyByYear.get(lastSolar.period);
const solarCapacityMultiple = lastSolarYear.solar_capacity_gw / firstSolarYear.solar_capacity_gw;
const solarCaptureCorr = capacityCorrelation.find((d) => d.x === "solar_capacity_gw" && d.y === "solar_capture_rate");
const spreadCorr = capacityCorrelation.find((d) => d.x === "solar_capacity_gw" && d.y === "spread_pct_of_price");
const windCaptureCorr = capacityCorrelation.find((d) => d.x === "wind_capacity_gw" && d.y === "wind_capture_rate");
const solarTarget = extrapolationFlags.find((d) => d.technology === "Solar AC");
const solarDcTarget = extrapolationFlags.find((d) => d.technology === "Solar DC");
const windOnshoreTarget = extrapolationFlags.find((d) => d.technology === "Wind onshore");
const windOffshoreTarget = extrapolationFlags.find((d) => d.technology === "Wind offshore");
const foresightCompetition = competitionCorrelation.find((d) => d.strategy === "perfect_foresight" && d.energy_mwh === duration);
```

**Solar is still deepening the trough.** Solar's capture rate fell from
**${pct(firstSolar.capture_rate)}** in ${firstSolar.period} to
**${pct(lastSolar.capture_rate)}** in ${lastSolar.period} (partial year) as
installed solar grew about ${solarCapacityMultiple.toFixed(1)}×, and on-peak
hours now clear below off-peak on average: the signature of solar
cannibalisation. Wind shows no comparable trend. With
${solarCaptureCorr.n} complete years, these correlations
(${solarCaptureCorr.pearson_r.toFixed(2)} for solar capture,
${windCaptureCorr.pearson_r.toFixed(2)} for wind) describe co-movement, not
causation. The 2030 targets, ${gw(solarTarget.planned_2030_gw)} GW of solar
against a recorded ${gw(solarTarget.realised_max_gw)} GW AC
(${gw(solarDcTarget.realised_max_gw)} GW DC) in ${solarTarget.realised_max_year},
lie well beyond the range these data cover.

**Competing storage has not yet compressed the day-ahead margin, but that may
change.** For the ${duration}-hour battery, the perfect-foresight margin has
risen with Germany's battery fleet (r=${foresightCompetition.pearson_r.toFixed(2)},
n=${foresightCompetition.n} years). Over so few years, with the gas shock in the
sample, this cannot rule out a competition effect. The shallow balancing markets
are where a larger fleet would press first, and the day-ahead spread is the only
market deep enough to absorb it, which makes that spread the one to watch.
Storage packs are getting cheaper: global stationary-storage pack prices fell 45%
in 2025 to $70/kWh ([BloombergNEF, December 2025](https://about.bnef.com/insights/clean-transport/lithium-ion-battery-pack-prices-fall-to-108-per-kilowatt-hour-despite-rising-metal-prices-bloombergnef/)),
which lowers the barrier to new capacity. A calmer gas market or a large build of
grid-scale storage would shrink the spread itself, not just the forecast's edge.

<details>
<summary>Dispatch rules and study boundaries</summary>

- **Dispatch:** one full-day schedule chosen from the forecast at the gate, then
  settled at realised prices; no intraday re-optimisation. At most one
  charge–discharge episode a day in the base case, 1 MW power, 90% round-trip
  efficiency, a 0.25 MWh state-of-charge grid, and an empty battery at the start
  and end of each day. Perfect foresight uses the same optimiser on realised
  prices; no trade is the zero alternative.
- **Sample:** all strategies share ${coverage[0].common_days} complete days out
  of ${coverage[0].candidate_days} candidates. Incomplete days and ambiguous
  clock-change days are excluded, not imputed. Forecasts are rounded to cents
  before dispatch.
- **Revenue stack:** a German battery can also trade continuous intraday and
  sell balancing capacity and energy (FCR, aFRR and mFRR, tendered through
  [regelleistung.net](https://www.regelleistung.net/)). Those markets are not
  modelled, nor is the trade-off that capacity committed to balancing cannot
  arbitrage at the same time.
- **Evidence:** retrospective, on history inspected during development.
  Historical inputs carry provider revisions. Market impact, imbalance
  settlement, capital costs and financing are not modelled. See the
  [forecast protocol](./forecast) and [methodology](./methodology).

</details>
