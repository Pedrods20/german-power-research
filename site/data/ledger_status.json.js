// Pilot counter, computed at build time from the committed attempt records: ledger
// commits trigger no deploy, so an exported table would go stale between releases.
// Each delivery day counts once per arm, at the best outcome any attempt reached;
// `already_issued` confirms an issue and is not counted. The retired `ridge_da`
// keeps its records but is not a pilot arm.

import {existsSync, readFileSync, readdirSync} from "node:fs";
import {fileURLToPath} from "node:url";

const root = fileURLToPath(new URL("../../data/forecast_issues/attempts/", import.meta.url));
const rank = {issued: 5, partial: 4, abstained: 3, late: 2, failed: 1, started: 0};
const order = ["ridge", "naive_previous_day", "naive_previous_week", "naive_similar_day"];

const read = (path) => JSON.parse(readFileSync(path, "utf8"));
const attempts = (existsSync(root) ? readdirSync(root) : [])
  .filter((id) => existsSync(`${root}${id}/started.json`))
  .map((id) => {
    const started = read(`${root}${id}/started.json`);
    const done = `${root}${id}/completed.json`;
    return {...started, ...(existsSync(done) ? read(done) : {status: "started"})};
  });

const days = new Map(); // model -> Map(delivery_date -> best status)
let asOf = null;
for (const a of attempts) {
  const stamp = a.completed_at ?? a.started_at;
  if (!asOf || stamp > asOf) asOf = stamp;
  if (!(a.status in rank) || !order.includes(a.model)) continue;
  const perModel = days.get(a.model) ?? new Map();
  const best = perModel.get(a.delivery_date);
  if (best === undefined || rank[a.status] > rank[best]) perModel.set(a.delivery_date, a.status);
  days.set(a.model, perModel);
}

const arms = [...days.keys()]
  .sort((a, b) => order.indexOf(a) - order.indexOf(b))
  .map((model) => {
    const outcomes = [...days.get(model).values()];
    const count = (status) => outcomes.filter((s) => s === status).length;
    const dates = [...days.get(model).keys()].sort();
    return {
      model,
      days: outcomes.length,
      issued: count("issued"),
      partial: count("partial"),
      abstained: count("abstained"),
      late: count("late"),
      failed: count("failed") + count("started"),
      first_delivery: dates[0],
      last_delivery: dates.at(-1)
    };
  });

process.stdout.write(JSON.stringify({as_of: asOf, attempts: attempts.length, arms}, null, 2));
