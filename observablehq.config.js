export default {
  // The framework defaults to "src", which holds the Python package.
  root: "site",
  title: "German Power Market Research",

  pages: [
    { name: "Forecast evidence", path: "/forecast" },
    { name: "Storage value", path: "/battery" },
    { name: "Methodology", path: "/methodology" },
  ],

  theme: ["air", "near-midnight"],
  toc: true,
  sidebar: true,
  pager: true,
  typographicQuotes: true,

  // Favicon: the daily price shape, inline.
  head: `<link rel="icon" href="data:image/svg+xml,${encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">' +
      '<rect width="32" height="32" rx="6" fill="#0b1b2b"/>' +
      '<path d="M3 12 L9 10 L13 22 L19 6 L23 14 L29 11" fill="none" ' +
      'stroke="#F0E442" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>' +
      "</svg>",
  )}">
<style>
/* Site-wide: wide tables scroll inside themselves and long inline code wraps,
   so no page scrolls sideways on a phone. */
main.observablehq > table { display: block; max-width: 100%; overflow-x: auto; }
main.observablehq p code, main.observablehq li code { overflow-wrap: anywhere; }
</style>`,

  header: "",
  footer: ({ path }) =>
    `Built from primary system-operator data. ` +
    `<a href="https://github.com/Pedrods20/german-power-research">Source and methodology on GitHub</a>.`,

  // Project pages are served under /<repository>/.
  base: process.env.GPA_BASE_PATH ?? "/",

  search: true,
};
