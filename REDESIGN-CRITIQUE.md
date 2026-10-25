# Redesign Critique, Exception Tracker (Blueprint board + English pass)

Redesign executed 2026-10-24 against `DESIGN-RESEARCH.md` §3.12 and the
18-item anti-list. This file is the evidence record.

## What changed

- `tracker.py`: the HTML report was rebuilt from a Georgia-and-cards page
  with one SVG bar chart into a Blueprint Spatial Board, engineering blue
  `#123A6B` on `#0C2A50`, white line work over a 25-unit drawing grid,
  Space Grotesk for zone names, IBM Plex Mono for ids, coordinates and the
  title block. Every shipment plots as a node inside its zone region;
  exceptions are signal-orange `#FF7A1A` nodes with an SVG route line drawn
  node → courier → station (draw-on, 550ms, staggered, killed under
  `prefers-reduced-motion`). Hovering a route lights it orange and dims
  the rest of the board to 35%, done in pure CSS (`:has()`), no JavaScript.
  The sheet closes with an engineering title block: checked/act-today
  counts, the live rule thresholds from the run's own config, and the
  source filename. Below the board, the act-today actions and the
  malformed/duplicate field notes.
- Data model, additive only: the report reads two **optional** columns,
  `zone` and `courier`, when the input provides them. Classification never
  looks at them. Without them a shipment plots in an "Unzoned" region and
  its route runs straight to the station. `sample_shipments.csv` gained
  both columns (Tanta East, Zefta, El Mahalla, Kafr El Zayat; Couriers
  A/B/C) so the bundled demo draws a real board.
- `tests/test_tracker.py`: the one HTML assertion updated from "SVG chart
  by action type" to the board's real markers (board title, a plotted
  route's action type, Space Grotesk, the UNZONED fallback region, the
  fixture deliberately ships no zone column, so the fallback is itself
  under test).
- `README.md`: `--report` description rewritten, optional columns
  documented.
- `DESIGN.md`: added.
- Language: CLI output, sample data and README were already English;
  verified end to end.

## Evidence

- Tests: **19/19 before, 19/19 after** (`python3 tests/test_tracker.py`).
- Numbers unchanged: the sample run's terminal output after the redesign
  is byte-identical to the pre-redesign baseline (diff clean, excluding
  the "HTML report written" notice), **6 shipments checked, 4 need action
  today**, the same four (S-902 call_customer_window, S-903 open_trace,
  S-904 reship_or_refund, S-906 escalate_supervisor) with the same actions.
- The generated board contains exactly **4 route groups** and its title
  block reads "CHECKED 6 · ACT TODAY 4", matching the run.
- Classification logic untouched: `classify`, `action_for`, `row_problem`,
  `load_shipments` and `collect_exceptions` are byte-for-byte what they
  were; only the report writer, its call site, and the sample's two extra
  columns changed.

## Anti-list items killed in this project

One-long-page card stack (6), KPI row (5), rounded-everything (4),
traffic-light palette (7, white/orange drawing logic instead), no brand
mark (17, the drawn compass mark), proportional numbers (16), absent
motion (18, draw-on routes that encode the route itself, with a
reduced-motion path).

## Honest gaps

- Board geometry is a fixed 1000×620 drawing that scales down as one
  sheet; on a narrow phone it stays legible as a drawing but small, the
  same trade a paper wall chart makes. The detailed act-today list below
  the board is the small-screen reading path.
- Zone regions use a quadrant layout up to four zones and a plain grid
  beyond that; with many zones and many shipments per zone, node slots
  (three per row inside a region) will crowd before they break. Real
  stations run a handful of zones, which is what this is drawn for.
- Headless Chromium in this VM hangs on screenshot capture (two attempts),
  so the board was verified by markup inspection, route counts and test
  assertions, not by a rendered screenshot. Hover behaviour relies on
  `:has()`, universal in browsers since 2023, but it has not been clicked
  through on a physical device in this pass.
