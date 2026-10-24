#!/usr/bin/env python3
import argparse, csv, html, json, logging, os, sys
from collections import Counter

REQUIRED_COLUMNS = ["shipment_id", "status", "days_in_transit", "delivery_attempts", "customer_phone"]
VALID_STATUSES = {"in_transit", "out_for_delivery", "delivered", "returned"}
log = logging.getLogger("exception_tracker")


def thresholds_from_env():
    return {
        "stuck_days": int(os.environ.get("TRACKER_STUCK_DAYS", "5")),
        "pin_attempts": int(os.environ.get("TRACKER_PIN_ATTEMPTS", "2")),
        "escalate_attempts": int(os.environ.get("TRACKER_ESCALATE_ATTEMPTS", "3")),
    }


def classify(s, th=None):
    # Returns (action type, action text) or None when the parcel is moving normally.
    th = th or thresholds_from_env()
    attempts = int(s.get("delivery_attempts") or 0)
    days = int(s.get("days_in_transit") or 0)
    status = (s.get("status") or "").strip().lower()
    if status == "returned":
        return "reship_or_refund", "Call customer today: reship with verified address or refund. Do not reship blind."
    if attempts >= th["escalate_attempts"]:
        return "escalate_supervisor", "Escalate to courier supervisor and call customer to fix address/landmark."
    if status == "out_for_delivery" and attempts >= th["pin_attempts"]:
        return "call_customer_window", "Call customer before the third attempt and pin a time window."
    if days >= th["stuck_days"] and status == "in_transit":
        return "open_trace", "Open a trace with the courier today; parcel is stuck, not moving."
    return None


def action_for(s, th=None):
    found = classify(s, th)
    return found[1] if found else None


def row_problem(raw):
    if None in raw or any(v is None for v in raw.values()):
        return "wrong number of fields for the header"
    if not (raw.get("shipment_id") or "").strip():
        return "shipment_id is empty"
    status = (raw.get("status") or "").strip().lower()
    if status not in VALID_STATUSES:
        return f"status '{raw.get('status')}' is not a known shipment status"
    for col in ("days_in_transit", "delivery_attempts"):
        val = (raw.get(col) or "").strip()
        try:
            if int(val) < 0:
                return f"{col} is negative"
        except ValueError:
            return f"{col} value '{val}' is not a whole number"
    if not (raw.get("customer_phone") or "").strip():
        return "customer_phone is empty, the follow up call has nowhere to go"
    return None


def load_shipments(path):
    clean, malformed, duplicates = [], [], []
    seen = {}
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError("file is empty, no header row found")
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError("missing required columns: " + ", ".join(missing))
        for lineno, raw in enumerate(reader, start=2):
            reason = row_problem(raw)
            if reason:
                malformed.append({"row": lineno, "reason": reason, "data": {k: v for k, v in raw.items() if k}})
                log.warning("malformed row %s: %s", lineno, reason)
                continue
            sid = raw["shipment_id"].strip()
            if sid in seen:
                duplicates.append({"row": lineno, "shipment_id": sid, "first_row": seen[sid]})
                log.warning("duplicate shipment_id %s on row %s, first seen on row %s", sid, lineno, seen[sid])
                continue
            seen[sid] = lineno
            clean.append(raw)
    return clean, malformed, duplicates


def collect_exceptions(rows, th=None):
    flagged = []
    for r in rows:
        found = classify(r, th)
        if found:
            flagged.append({"shipment": r, "action_type": found[0], "action": found[1]})
    return flagged


def zone_of(s):
    return (s.get("zone") or "Unzoned").strip() or "Unzoned"


def board_svg(rep, source_name):
    # Position is data on this board: a node sits inside its real zone, and its route
    # runs node to courier to station. Nothing is placed for decoration.
    shipments = rep.get("all_shipments", [])
    flagged = {f["shipment"]["shipment_id"]: f for f in rep["exceptions"]}
    zones = []
    for s in shipments:
        if zone_of(s) not in zones:
            zones.append(zone_of(s))
    couriers = []
    for s in shipments:
        c = (s.get("courier") or "").strip()
        if c and c not in couriers:
            couriers.append(c)
    import math
    station = (500, 240)
    courier_pos = {}
    for i, c in enumerate(couriers):
        ang = math.radians(-90 + i * 360 / max(1, len(couriers)))
        courier_pos[c] = (station[0] + 104 * math.cos(ang), station[1] + 104 * math.sin(ang))
    regions = {}
    if len(zones) <= 4:
        quads = [(28, 28, 440, 190), (532, 28, 440, 190), (28, 262, 440, 190), (532, 262, 440, 190)]
        for i, z in enumerate(zones):
            regions[z] = quads[i]
    else:
        cols = 3
        rows_n = math.ceil(len(zones) / cols)
        cw, ch = (972 - 28) / cols, (452 - 28) / rows_n
        for i, z in enumerate(zones):
            regions[z] = (28 + (i % cols) * cw + 6, 28 + (i // cols) * ch + 6, cw - 12, ch - 12)
    out = ['<svg class="board" viewBox="0 0 1000 620" xmlns="http://www.w3.org/2000/svg" role="img" '
           'aria-label="exception board: shipments plotted by zone">']
    out.append('<defs><pattern id="grid" width="25" height="25" patternUnits="userSpaceOnUse">'
               '<path d="M25 0 H0 V25" fill="none" stroke="#FFFFFF" stroke-opacity="0.12" stroke-width="1"/></pattern></defs>')
    out.append('<rect x="0" y="0" width="1000" height="620" fill="#123A6B"/>')
    out.append('<rect x="0" y="0" width="1000" height="470" fill="url(#grid)"/>')
    zone_count = Counter(zone_of(s) for s in shipments)
    zone_flag = Counter(zone_of(f["shipment"]) for f in rep["exceptions"])
    for zi, z in enumerate(zones):
        x, y, w, h = regions[z]
        grid_ref = f"{'ABCD'[zi % 4]}{1 + zi // 4}"
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#FFFFFF" stroke-opacity="0.55"/>')
        out.append(f'<text x="{x + 14}" y="{y + 26}" class="zname">{html.escape(z.upper())}</text>')
        out.append(f'<text x="{x + 14}" y="{y + 44}" class="zmeta">GRID {grid_ref} · {zone_count[z]} SHIPMENTS · '
                   f'{zone_flag.get(z, 0)} ACT TODAY</text>')
    sx, sy = station
    out.append(f'<g class="station"><rect x="{sx - 24}" y="{sy - 24}" width="48" height="48" fill="#123A6B" '
               'stroke="#FFFFFF" stroke-width="1.6"/>'
               f'<rect x="{sx - 24}" y="{sy - 24}" width="48" height="48" fill="none" stroke="#FFFFFF" '
               'stroke-opacity="0.35" transform="translate(5 5)"/>'
               f'<text x="{sx}" y="{sy + 40}" class="stext" text-anchor="middle">STATION</text></g>')
    for c, (cx, cy) in courier_pos.items():
        out.append(f'<g class="courier"><circle cx="{cx:.0f}" cy="{cy:.0f}" r="8" fill="#123A6B" stroke="#FFFFFF"/>'
                   f'<text x="{cx + 13:.0f}" y="{cy + 4:.0f}" class="ctext">{html.escape(c.upper())}</text></g>')
    per_zone_seen = Counter()
    route_i = 0
    for s in shipments:
        z = zone_of(s)
        x0, y0, w, h = regions[z]
        idx = per_zone_seen[z]
        per_zone_seen[z] += 1
        slot_w = (w - 56) / 3
        nx = x0 + 28 + slot_w * (idx % 3) + slot_w / 2
        ny = y0 + 78 + (idx // 3) * 58
        sid = s["shipment_id"]
        f = flagged.get(sid)
        label = (f'<text x="{nx + 16:.0f}" y="{ny + 4:.0f}" class="ntext">{html.escape(sid)}</text>')
        coord = f'<text x="{nx + 16:.0f}" y="{ny + 17:.0f}" class="coord">{nx:.0f},{ny:.0f}</text>'
        if f:
            c = (s.get("courier") or "").strip()
            pts = f'{nx:.0f},{ny:.0f} '
            if c in courier_pos:
                pts += f'{courier_pos[c][0]:.0f},{courier_pos[c][1]:.0f} '
            pts += f'{sx},{sy}'
            out.append(f'<g class="route"><polyline points="{pts}" fill="none" stroke="#FFFFFF" '
                       f'stroke-opacity="0.75" stroke-width="1.4" pathLength="1" '
                       f'style="stroke-dasharray:1;stroke-dashoffset:1;animation-delay:{route_i * 110}ms"/>'
                       f'<circle cx="{nx:.0f}" cy="{ny:.0f}" r="10" fill="#FF7A1A" stroke="#FFFFFF" stroke-width="1.4"/>'
                       f'{label}{coord}</g>')
            route_i += 1
        else:
            out.append(f'<g class="plain"><circle cx="{nx:.0f}" cy="{ny:.0f}" r="7" fill="none" '
                       f'stroke="#FFFFFF" stroke-opacity="0.6"/>{label}{coord}</g>')
    th = rep.get("config", {}).get("thresholds", {})
    out.append('<g class="titleblock">'
               '<rect x="556" y="486" width="416" height="118" fill="none" stroke="#FFFFFF"/>'
               '<line x1="556" y1="516" x2="972" y2="516" stroke="#FFFFFF" stroke-opacity="0.6"/>'
               '<line x1="556" y1="546" x2="972" y2="546" stroke="#FFFFFF" stroke-opacity="0.6"/>'
               '<line x1="556" y1="576" x2="972" y2="576" stroke="#FFFFFF" stroke-opacity="0.6"/>'
               '<text x="570" y="507" class="tb1">EXCEPTION TRACKER — SHIPMENT EXCEPTION BOARD</text>'
               f'<text x="570" y="537" class="tb2">CHECKED {rep["total_shipments"]} · ACT TODAY {rep["exception_count"]}</text>'
               f'<text x="570" y="567" class="tb2">RULES: STUCK ≥ {th.get("stuck_days", 5)}D · PIN ≥ {th.get("pin_attempts", 2)} ATT · '
               f'ESCALATE ≥ {th.get("escalate_attempts", 3)} ATT</text>'
               f'<text x="570" y="597" class="tb2">DRAWN FROM {html.escape(source_name)}</text></g>')
    tally = " · ".join(f"{k} ×{v}" for k, v in sorted(rep["by_action_type"].items(), key=lambda kv: -kv[1]))
    out.append(f'<text x="28" y="507" class="tb1">ACT TODAY, BY ACTION</text>')
    out.append(f'<text x="28" y="533" class="tbact">{html.escape(tally) if tally else "none"}</text>')
    out.append(f'<text x="28" y="567" class="tb2">ORANGE NODES NEED A HUMAN TODAY. WHITE OUTLINES ARE MOVING NORMALLY.</text>')
    out.append("</svg>")
    return "\n".join(out)


def write_html_report(rep, path, source_name="shipments.csv"):
    bad = "".join(f"<li>Row {m['row']}: {html.escape(m['reason'])}</li>" for m in rep["malformed_rows"]) or "<li>None</li>"
    dup = "".join(f"<li>Row {d['row']}: shipment_id {html.escape(d['shipment_id'])} duplicates row {d['first_row']}</li>"
                  for d in rep["duplicates"]) or "<li>None</li>"
    acts = "".join(
        f'<li><span class="aid">{html.escape(f["shipment"]["shipment_id"])}</span>'
        f'<span class="atype">{html.escape(f["action_type"])}</span>'
        f'<span class="aact">{html.escape(f["action"])}</span></li>' for f in rep["exceptions"]) or "<li>Nothing needs action today.</li>"
    mark = ('<svg width="34" height="34" viewBox="0 0 34 34" xmlns="http://www.w3.org/2000/svg" role="img" '
            'aria-label="exception tracker compass mark"><circle cx="17" cy="17" r="14.5" fill="none" '
            'stroke="#FFFFFF" stroke-width="1.6"/><path d="M17 6 L20 17 L17 28 L14 17 Z" fill="#FF7A1A"/>'
            '<circle cx="17" cy="17" r="2.2" fill="#FFFFFF"/></svg>')
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Exception Board — shipments that need a human today</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#0C2A50;color:#FFFFFF;font-family:"Space Grotesk",system-ui,sans-serif;
font-variant-numeric:tabular-nums}}
.page{{max-width:1060px;margin:0 auto;padding:44px 22px 72px}}
.top{{display:flex;gap:16px;align-items:center;margin-bottom:8px}}
h1{{font-size:30px;font-weight:700;letter-spacing:.04em;margin:0}}
.sub{{font-family:"IBM Plex Mono",monospace;font-size:12.5px;color:#BFD4F2;margin:6px 0 22px}}
.board{{width:100%;height:auto;display:block;border:1px solid rgba(255,255,255,.55)}}
.board text{{fill:#FFFFFF}}
.zname{{font-family:"Space Grotesk",sans-serif;font-size:17px;font-weight:700;letter-spacing:.14em}}
.zmeta,.coord{{font-family:"IBM Plex Mono",monospace;font-size:10px;fill:#BFD4F2 !important}}
.ntext,.ctext{{font-family:"IBM Plex Mono",monospace;font-size:11.5px}}
.stext{{font-family:"IBM Plex Mono",monospace;font-size:10.5px;letter-spacing:.18em}}
.tb1{{font-family:"IBM Plex Mono",monospace;font-size:12px;font-weight:500;letter-spacing:.08em}}
.tb2{{font-family:"IBM Plex Mono",monospace;font-size:11.5px;fill:#BFD4F2 !important}}
.tbact{{font-family:"IBM Plex Mono",monospace;font-size:12.5px;fill:#FF7A1A !important}}
.route polyline{{animation:draw .55s cubic-bezier(.2,0,0,1) both}}
@keyframes draw{{to{{stroke-dashoffset:0}}}}
.board:has(.route:hover) .route:not(:hover){{opacity:.35}}
.board:has(.route:hover) .plain{{opacity:.35}}
.route:hover polyline{{stroke:#FF7A1A;stroke-opacity:1;stroke-width:2.6}}
.route:hover circle{{stroke-width:2.4}}
h2{{font-size:13px;letter-spacing:.22em;margin:40px 0 14px;font-weight:700}}
ul.acts{{list-style:none;margin:0;padding:0;border-top:1px solid rgba(255,255,255,.35)}}
ul.acts li{{display:flex;gap:20px;padding:11px 2px;border-bottom:1px solid rgba(255,255,255,.18);align-items:baseline;flex-wrap:wrap}}
.aid{{font-family:"IBM Plex Mono",monospace;color:#FF7A1A;flex:0 0 8ch}}
.atype{{font-family:"IBM Plex Mono",monospace;font-size:12px;color:#BFD4F2;flex:0 0 24ch}}
.aact{{font-size:15.5px}}
.notes{{font-family:"IBM Plex Mono",monospace;font-size:12px;color:#BFD4F2;line-height:1.9}}
.notes ul{{margin:0;padding-left:18px}}
@media (prefers-reduced-motion: reduce){{.route polyline{{animation:none;stroke-dashoffset:0 !important}}}}
@media print{{body{{background:#123A6B;-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
</style></head><body>
<main class="page">
<div class="top">{mark}<h1>EXCEPTION BOARD</h1></div>
<p class="sub">station wall chart · {rep['total_shipments']} shipments checked · {rep['exception_count']} need action today · routes drawn from each exception to its courier and the station</p>
{board_svg(rep, source_name)}
<h2>ACT TODAY</h2>
<ul class="acts">{acts}</ul>
<h2>FIELD NOTES</h2>
<div class="notes"><p>Malformed rows</p><ul>{bad}</ul><p>Duplicate shipments</p><ul>{dup}</ul></div>
</main></body></html>"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)


def main(argv=None):
    ap = argparse.ArgumentParser(description="List shipment exceptions that need a human today.")
    ap.add_argument("csv_file")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--report", dest="report_out", help="write a standalone HTML report")
    ap.add_argument("--strict", action="store_true", help="exit with code 2 when malformed or duplicate rows are found")
    ap.add_argument("--log", dest="log_file", default=os.environ.get("TRACKER_LOG_FILE", "tracker.log"))
    args = ap.parse_args(argv)
    logging.basicConfig(filename=args.log_file, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    log.info("run started")
    th = thresholds_from_env()
    try:
        rows, malformed, duplicates = load_shipments(args.csv_file)
    except (OSError, ValueError) as exc:
        log.error("cannot read input: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 2
    flagged = collect_exceptions(rows, th)
    print(f"{len(rows)} shipments checked, {len(flagged)} need action today.\n")
    for f in flagged:
        r = f["shipment"]
        print(f"{r['shipment_id']}  status={r['status']}  days={r['days_in_transit']}  attempts={r['delivery_attempts']}  action_type={f['action_type']}")
        print(f"  -> {f['action']}\n")
    if malformed:
        print(f"Malformed rows skipped: {len(malformed)}")
        for m in malformed:
            print(f"  row {m['row']}: {m['reason']}")
    if duplicates:
        print(f"\nDuplicate shipments skipped: {len(duplicates)}")
        for d in duplicates:
            print(f"  row {d['row']}: shipment_id {d['shipment_id']} duplicates row {d['first_row']}")
    rep = {
        "total_shipments": len(rows),
        "exception_count": len(flagged),
        "by_action_type": dict(Counter(f["action_type"] for f in flagged)),
        "exceptions": [{"shipment_id": f["shipment"]["shipment_id"], "action_type": f["action_type"], "action": f["action"]}
                       for f in flagged],
        "malformed_rows": malformed,
        "duplicates": duplicates,
        "config": {"thresholds": th, "log_file": args.log_file},
    }
    log.info("checked %s clean rows, %s exceptions, %s malformed, %s duplicates",
             len(rows), len(flagged), len(malformed), len(duplicates))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=2)
        print(f"JSON report written to {args.json_out}")
    if args.report_out:
        full = dict(rep)
        full["exceptions"] = flagged
        full["all_shipments"] = rows
        write_html_report(full, args.report_out, os.path.basename(args.csv_file))
        print(f"HTML report written to {args.report_out}")
    if args.strict and (malformed or duplicates):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
