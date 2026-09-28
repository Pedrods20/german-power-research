---
title: Forecast evidence
---

# Day-ahead forecasting: accuracy and limits

Five models forecast the hourly DE-LU day-ahead price using only what a bidder
knows when the order book closes at 12:00 on the day before delivery. Per-hour
Ridge regression is the most accurate overall and holds up best in the tail
hours that drive storage value. The more complex pooled LightGBM model is close
in ordinary hours but breaks down in negative-price and scarcity hours: model
complexity did not buy tail performance.

```js
const metadata = await FileAttachment("data/forecast.json").json();
const run = metadata.runs.find((d) => d.zone === "DE-LU");
const scores = [...await FileAttachment("data/forecast_scores.parquet").parquet()];
const daily = [...await FileAttachment("data/forecast_daily.parquet").parquet()];
const predictions = [...await FileAttachment("data/forecast_preview.parquet").parquet()];
const names = new Map([
  ["naive_previous_day", "Previous day"],
  ["naive_previous_week", "Previous week"],
  ["naive_similar_day", "Similar day"],
  ["ridge", "Ridge"],
  ["lightgbm", "LightGBM"],
]);
const label = (m) => names.get(m) ?? m;
const number = (v) => v == null ? "n/a" : v.toFixed(2);
const percent = (v) => v == null ? "n/a" : `${v.toFixed(1)}%`;
const overall = scores.filter((d) => d.scope === "overall").sort((a, b) => a.mae - b.mae);
const ridge = overall.find((d) => d.model === "ridge");
const trees = overall.find((d) => d.model === "lightgbm");
const color = {domain: [...names.values()], range: ["#999999", "#CC79A7", "#009E73", "#0072B2", "#D55E00"], legend: true};
```

<p class="note">Retrospective benchmark, ${run.test_start} to ${run.test_end}, on history inspected during development. It is not a record of forecasts issued before delivery; the prospective pilot is reported at the end of this page.</p>

## Results

```js
Inputs.table(overall.map((d) => ({
  Model: label(d.model), Hours: d.n, MAE: d.mae, RMSE: d.rmse,
  Bias: d.bias, "Skill vs best naive": d.skill_vs_best_baseline_pct,
})), {format: {MAE: number, RMSE: number, Bias: number, "Skill vs best naive": percent}, layout: "auto"})
```

```js
Plot.plot({
  title: `Ridge cuts the best naive forecast's error by ${percent(ridge.skill_vs_best_baseline_pct)}`,
  subtitle: "Mean absolute error, EUR/MWh. Lower is better. All models are scored on the same hours.",
  width, height: 250, marginLeft: 110,
  x: {label: "MAE, EUR/MWh", grid: true}, y: {label: null, domain: overall.map((d) => label(d.model))},
  color,
  marks: [Plot.barX(overall, {x: "mae", y: (d) => label(d.model), fill: (d) => label(d.model), tip: true}), Plot.ruleX([0])],
})
```

Ridge's mean absolute error is **${number(ridge.mae)} EUR/MWh**, against
${number(trees.mae)} for LightGBM. Skill is the share of the best naive
forecast's error that a model removes; bias is the realised price minus the
forecast, so a positive bias means the model forecasts too low. Accuracy is not
money: an error cut in flat hours is worth little to a battery. The
[storage page](./battery) converts these forecasts into dispatch margin.

<div class="note">

**Controls against look-ahead.** The forecast uses only data public before
12:00 on D-1: lagged prices, the calendar and residual load from two days
earlier. Model settings are frozen before the test window, and every refit uses
only earlier days. Published numbers come from a committed, hashed release that
`gpa export --check` verifies against the site. Live forecasts that miss the
gate are refused, never backdated.

</div>

## Does it pick the right hours?

```js
const decisions = [...await FileAttachment("data/forecast_decisions.parquet").parquet()];
const decision = (model) => decisions.find((d) => d.model === model);
const pickRidge = decision("ridge");
const pickNaive = decision("naive_similar_day");
```

```js
Inputs.table(["ridge", "lightgbm", "naive_similar_day", "naive_previous_day"].map((m) => decision(m)).map((d) => ({
  Model: label(d.model),
  "Cheapest hour, ±1h": d.trough_hit_pct,
  "Dearest hour, ±1h": d.peak_hit_pct,
  "Spread error (EUR/MWh)": d.spread_mae,
  "Negative hours caught": d.point_recall_pct,
  "q10 < 0 flag: caught": d.risk_recall_pct,
  "q10 < 0 flag: right": d.risk_precision_pct,
})), {format: {"Cheapest hour, ±1h": percent, "Dearest hour, ±1h": percent, "Spread error (EUR/MWh)": number, "Negative hours caught": percent, "q10 < 0 flag: caught": percent, "q10 < 0 flag: right": percent}, layout: "auto"})
```

A battery needs the order of the hours more than their level. Ridge places the
day's cheapest hour within an hour of the realised one on
**${percent(pickRidge.trough_hit_pct)}** of days and the dearest on
**${percent(pickRidge.peak_hit_pct)}**, against ${percent(pickNaive.trough_hit_pct)}
and ${percent(pickNaive.peak_hit_pct)} for the similar-day forecast. It is weak on
negative prices: its point forecast goes below zero for only
${percent(pickRidge.point_recall_pct)} of the ${pickRidge.negative_hours.toLocaleString("en")}
negative hours. Its lower quantile does better as a risk flag, catching
${percent(pickRidge.risk_recall_pct)} of them at ${percent(pickRidge.risk_precision_pct)}
precision. Like most regressions it also shrinks extremes: its daily spread is
${number(-pickRidge.spread_bias)} EUR/MWh narrower than the realised one on
average.

## Where the models fail

```js
const byYear = (model) => scores.filter((d) => d.scope === "year" && d.model === model).sort((a, b) => a.bucket.localeCompare(b.bucket));
const ridgeYearly = byYear("ridge");
const lightgbmYearly = byYear("lightgbm");
const worstYear = ridgeYearly.reduce((a, b) => (b.mae > a.mae ? b : a));
const calmestYear = ridgeYearly.reduce((a, b) => (b.mae < a.mae ? b : a));
const lightgbmLossYears = lightgbmYearly.filter((d) => d.skill_vs_best_baseline_pct <= 0).map((d) => d.bucket);
const recentYears = lightgbmYearly.filter((d) => d.bucket >= "2024" && d.bucket <= run.test_end.slice(0, 4));
const lightgbmAheadRecently = recentYears.every((d) => {
  const r = ridgeYearly.find((e) => e.bucket === d.bucket);
  return r && d.mae < r.mae;
});
const regime = (bucket) => scores.find((d) => d.scope === "regime" && d.bucket === bucket && d.model === "ridge");
const regimeOf = (bucket, model) => scores.find((d) => d.scope === "regime" && d.bucket === bucket && d.model === model);
const negative = regime("negative");
const scarcity = regime("scarcity");
```

**Complexity did not buy tail performance.** In the scarcest 5% of hours, Ridge still beats the best naive
forecast (${percent(scarcity.skill_vs_best_baseline_pct)}) while LightGBM loses
badly (${percent(regimeOf("scarcity", "lightgbm").skill_vs_best_baseline_pct)}). In
negative-price hours, both trail the best naive forecast: Ridge narrowly
(${percent(negative.skill_vs_best_baseline_pct)}), LightGBM by far
(${percent(regimeOf("negative", "lightgbm").skill_vs_best_baseline_pct)}). These
are the hours where a battery's margin is made or lost.

**Across years.** Ridge's error ranges from ${number(calmestYear.mae)} EUR/MWh in
${calmestYear.bucket} to ${number(worstYear.mae)} in ${worstYear.bucket}, the gas
crisis, with the same method throughout. LightGBM lost to the best naive in
${lightgbmLossYears.length ? lightgbmLossYears.join(" and ") : "no year"}, while
Ridge kept a positive margin every year.
${lightgbmAheadRecently ? "Since 2024, in a calmer market, LightGBM's annual error has been below Ridge's." : "LightGBM has not consistently closed the gap since."}

The comparison is between two specific designs: a separate linear model for
each hour, and one tree model pooled across hours, both with the same limited
inputs. It does not show that linear models generally beat tree models. It shows
that this pooled tree model did not extrapolate to price levels rarely seen in
training.

<details>
<summary>Breakdown by price regime, market block, year and hour</summary>

```js
const scope = view(Inputs.select(new Map([["Price regime", "regime"], ["Market block", "block"], ["Calendar year", "year"], ["Hour of day", "hour"]]), {label: "Break down by", value: "regime"}));
```

```js
const split = scores.filter((d) => d.scope === scope);
```

```js
Plot.plot({
  title: "Error by market condition", width,
  height: scope === "hour" ? 550 : 270, marginLeft: 100,
  x: {label: "MAE, EUR/MWh", grid: true}, y: {label: null}, color,
  marks: [Plot.dot(split, {x: "mae", y: "bucket", stroke: (d) => label(d.model), r: 5, tip: true}), Plot.ruleX([0])],
})
```

```js
Inputs.table(split.filter((d) => ["ridge", "lightgbm"].includes(d.model)).map((d) => ({
  Model: label(d.model), Bucket: d.bucket, Hours: d.n, MAE: d.mae, RMSE: d.rmse,
  Bias: d.bias, "Skill vs best naive": d.skill_vs_best_baseline_pct,
})), {format: {MAE: number, RMSE: number, Bias: number, "Skill vs best naive": percent}, layout: "auto"})
```

Negative-price hours and the top 5% of evaluation prices are regimes assigned
after the fact; they are never model inputs.

```js
const failures = scores.filter((d) => ["ridge", "lightgbm"].includes(d.model) && d.skill_vs_best_baseline_pct <= 0).sort((a, b) => a.skill_vs_best_baseline_pct - b.skill_vs_best_baseline_pct);
```

${failures.length} model–bucket comparisons show no improvement over the best
naive forecast. The breakdowns overlap, so these are not independent failures.

```js
const selectedModel = view(Inputs.select(new Map([["LightGBM", "lightgbm"], ["Ridge", "ridge"]]), {label: "Inspect model", value: "lightgbm"}));
```

```js
const modelDaily = daily.filter((d) => d.model === selectedModel);
```

```js
Plot.plot({
  title: `Daily error: ${label(selectedModel)}`, width, height: 260, marginLeft: 55,
  x: {type: "utc", label: null}, y: {label: "MAE, EUR/MWh", grid: true},
  marks: [Plot.lineY(modelDaily, {x: (d) => new Date(d.local_date), y: "mae", stroke: "#0072B2", tip: true})],
})
```

</details>

## Would operator forecasts help?

```js
const ablation = [...await FileAttachment("data/fundamentals_ablation.parquet").parquet()];
const ablationRow = (model, includeFundamentals) => ablation.find((d) => d.model === model && d.include_fundamentals === includeFundamentals);
const ridgeBase = ablationRow("ridge", false);
const ridgeAbl = ablationRow("ridge", true);
const lightgbmBase = ablationRow("lightgbm", false);
const lightgbmAbl = ablationRow("lightgbm", true);
```

Adding the operators' day-ahead forecasts of load, wind and solar, on the same
test window and protocol:

```js
ridgeBase && ridgeAbl && lightgbmBase && lightgbmAbl
  ? Inputs.table([
      {Model: "Ridge", "MAE, published": ridgeBase.mae, "MAE, with fundamentals": ridgeAbl.mae, "Change": (1 - ridgeAbl.mae / ridgeBase.mae) * 100},
      {Model: "LightGBM", "MAE, published": lightgbmBase.mae, "MAE, with fundamentals": lightgbmAbl.mae, "Change": (1 - lightgbmAbl.mae / lightgbmBase.mae) * 100},
    ], {format: {"MAE, published": number, "MAE, with fundamentals": number, "Change": percent}, layout: "auto"})
  : html`<p class="note">Ablation not yet run locally: <code>gpa fundamentals-ablation</code>.</p>`
```

They help, but this source cannot supply them in time. EU rules only require
wind and solar forecasts by 18:00 Brussels time on D-1, six hours after the
gate, and a probe of Energy-Charts found neither at checks two to nearly five
hours after the gate on each of the five delivery days it covered (25 to 29
September 2026). The gain is therefore an upper bound: it credits the model with
forecasts this public source only has hours after the auction. A desk closes
that gap with commercial forecasts issued before the gate.

<details>
<summary>Design: target, inputs and test protocol</summary>

- **Target:** the duration-weighted hourly average of DE-LU day-ahead prices, in
  EUR/MWh. Since delivery on 1 October 2025 the auction clears quarter-hours, so
  the hourly figure is an analytical aggregate rather than a traded product.
- **Gate:** 12:00 market time on D-1, when the order book closes. Prices for the
  previous delivery day have already cleared and are available.
- **Inputs:** lagged prices, calendar variables and residual load (demand minus
  wind and solar) from at least two delivery days earlier. Realised
  delivery-day values never enter a forecast.
- **Protocol:** training starts ${run.train_start} and validation
  ${run.validation_start}; the test runs from ${run.test_start} to
  ${run.test_end}. The ridge penalty and tree settings are chosen on the
  validation window and frozen. Every model refits using only dates before the
  forecast day. All five models are scored on the same
  ${run.scored_hours.toLocaleString("en")} hours out of
  ${run.eligible_hours.toLocaleString("en")} in the period.
- **Models:** Ridge fits one regression per delivery hour; LightGBM fits one
  model across hours, with the hour as a feature. The naive forecasts repeat the
  previous day, the previous week or the last similar day: what a desk falls
  back on without a model.
- **Data handling:** only complete hours enter the panel, and missing
  observations stay missing. The two occurrences of the autumn clock-change hour
  are averaged. Stored inputs carry the providers' latest revisions, so the
  exact values visible at each historical gate cannot be verified.

</details>

<details>
<summary>Predictive intervals</summary>

Each model's 80% interval uses quantiles of its own previous 56 errors at the
same clock hour; current-day errors never enter the calibration.

```js
const intervalRows = overall.map((d) => ({
  Model: label(d.model), Hours: d.n_interval,
  "Observed coverage": d.interval_coverage_pct,
  "Nominal coverage": 80, "Mean width (EUR/MWh)": d.interval_mean_width,
  "Mean pinball": d.mean_pinball,
}));
Inputs.table(intervalRows, {format: {"Observed coverage": percent, "Nominal coverage": percent, "Mean width (EUR/MWh)": number, "Mean pinball": number}, layout: "auto"})
```

Coverage falls short of the nominal 80% for every model. Pinball loss and
interval width are shown because a very wide interval can cover prices while
saying little.

</details>

<details>
<summary>Inspect a week</summary>

Twelve evenly spaced weeks from the test period.

```js
const weekModel = view(Inputs.select(new Map([["LightGBM", "lightgbm"], ["Ridge", "ridge"]]), {label: "Inspect model", value: "lightgbm"}));
```

```js
const weeks = [...new Set(predictions.map((d) => d3.utcMonday(new Date(d.local_date)).toISOString().slice(0, 10)))].sort();
```

```js
const week = view(Inputs.select(weeks, {label: "Week beginning", value: weeks[Math.floor(weeks.length / 2)]}));
```

```js
const begin = new Date(week);
const end = d3.utcDay.offset(begin, 7);
const weekRows = predictions.filter((d) => d.model === weekModel && new Date(d.local_date) >= begin && new Date(d.local_date) < end);
const stamp = (d) => d3.utcHour.offset(new Date(d.local_date), d.local_hour);
```

```js
Plot.plot({
  title: `${label(weekModel)} against realised hourly price`,
  subtitle: "Hourly forecast with its 80% interval.",
  width, height: 320, marginLeft: 55,
  x: {type: "utc", label: "market-local clock hour (displayed on a synthetic axis)"},
  y: {label: "EUR/MWh", grid: true},
  marks: [
    Plot.areaY(weekRows, {x: stamp, y1: "q10", y2: "q90", fill: "#0072B2", fillOpacity: .15}),
    Plot.lineY(weekRows, {x: stamp, y: "forecast", stroke: "#0072B2", tip: true}),
    Plot.lineY(weekRows, {x: stamp, y: "actual", stroke: "currentColor", tip: true}),
    Plot.ruleY([0]),
  ],
})
```

</details>

## Prospective pilot

Since 23 September 2026, a scheduled job issues Ridge and the three naive
forecasts before each gate and stores the inputs each forecast used. Runs that
arrive after the gate are refused rather than backdated. A second Ridge arm with
the operator forecasts, `ridge_da`, found nothing to read in 11 pre-gate runs
across six delivery days and was retired on 28 September, for the reason above.
Each delivery day counts once, at the best outcome any attempt reached:

```js
const ledgerStatus = await FileAttachment("data/ledger_status.json").json();
```

```js
ledgerStatus.arms.length
  ? Inputs.table(ledgerStatus.arms, {
      columns: ["model", "days", "issued", "partial", "abstained", "late", "failed", "first_delivery", "last_delivery"],
      header: {model: "Arm", days: "Days tried", first_delivery: "First day", last_delivery: "Latest day"},
      layout: "auto"
    })
  : html`<p class="note">No attempt records in this build.</p>`
```

<p class="note">Ledger as of ${ledgerStatus.as_of ? ledgerStatus.as_of.slice(0, 16).replace("T", " ") + " UTC" : "—"}; the site is rebuilt on each release, not on each run. The pilot's bar is six weeks with at least 95% of delivery days issued on time. It tests whether the process runs reliably; it cannot establish economic value across seasons.</p>

<details>
<summary>Reproduce</summary>

```bash
pip install -e ".[dev]"
gpa backtest --scope all
gpa fundamentals-ablation
gpa export --check
```

The frozen release under `data/experiments/` stores the predictions, scores,
parameter searches, ridge coefficients and input panel, together with a hash of
the forecasting code. The input-panel SHA-256 is ${html`<code>${run.input_sha256}</code>`};
`gpa export --check` confirms every published table still matches it.

</details>

<style>
.note {
  border-left: 3px solid var(--theme-foreground-focus);
  padding: .5rem 0 .5rem 1rem;
  color: var(--theme-foreground-muted);
}
</style>
