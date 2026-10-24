#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tracker import action_for, collect_exceptions, load_shipments

RESULTS = []

def check(name, cond):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)

def write_csv(text):
    fh = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    fh.write(text); fh.close()
    return fh.name

HEADER = "shipment_id,status,days_in_transit,delivery_attempts,customer_phone\n"

def main():
    check("returned parcel gets the reship or refund action", "reship" in action_for({"status": "returned", "days_in_transit": "6", "delivery_attempts": "3"}))
    check("third attempt escalates to the supervisor", "supervisor" in action_for({"status": "out_for_delivery", "days_in_transit": "4", "delivery_attempts": "3"}))
    check("second out for delivery attempt pins a time window", "time window" in action_for({"status": "out_for_delivery", "days_in_transit": "3", "delivery_attempts": "2"}))
    check("five days in transit opens a trace", "trace" in action_for({"status": "in_transit", "days_in_transit": "7", "delivery_attempts": "0"}))
    check("a normal parcel needs no action", action_for({"status": "in_transit", "days_in_transit": "2", "delivery_attempts": "0"}) is None)
    custom = {"stuck_days": 2, "pin_attempts": 2, "escalate_attempts": 3}
    check("custom stuck threshold changes the verdict", "trace" in action_for({"status": "in_transit", "days_in_transit": "3", "delivery_attempts": "0"}, custom))

    good = write_csv(HEADER + "S-1,in_transit,7,0,01000000001\nS-2,delivered,3,1,01000000002\n")
    rows, malformed, dups = load_shipments(good)
    check("clean file loads with no complaints", len(rows) == 2 and malformed == [] and dups == [])
    flagged = collect_exceptions(rows)
    check("exceptions carry an action type", len(flagged) == 1 and flagged[0]["action_type"] == "open_trace")

    bad = write_csv(HEADER + "S-3,in_transit,seven,0,01000000003\nS-4,teleported,1,0,01000000004\n")
    rows, malformed, dups = load_shipments(bad)
    check("non numeric days are malformed with a row number", malformed[0]["row"] == 2 and "whole number" in malformed[0]["reason"])
    check("unknown status is malformed, not swallowed", len(malformed) == 2 and rows == [])

    dup_path = write_csv(HEADER + "S-9,returned,6,3,01000000009\nS-9,returned,6,3,01000000009\n")
    rows, malformed, dups = load_shipments(dup_path)
    check("duplicate shipment_id is reported and deduped", len(dups) == 1 and dups[0]["first_row"] == 2 and len(rows) == 1)

    try:
        load_shipments(write_csv("shipment_id,status\nS-1,in_transit\n")); raised = False
    except ValueError as exc:
        raised = "missing required columns" in str(exc)
    check("missing columns raise a clear error", raised)

    with tempfile.TemporaryDirectory() as td:
        src = write_csv(HEADER + "S-1,returned,6,3,01000000001\nS-2,out_for_delivery,4,3,01000000002\nS-2,returned,1,1,01000000002\nS-3,in_transit,oops,0,01000000003\n")
        out_json, out_html, out_log = os.path.join(td, "r.json"), os.path.join(td, "r.html"), os.path.join(td, "t.log")
        tool = os.path.join(os.path.dirname(__file__), "..", "tracker.py")
        proc = subprocess.run([sys.executable, tool, src, "--json", out_json, "--report", out_html, "--log", out_log],
                              capture_output=True, text=True)
        check("cli exits zero without strict", proc.returncode == 0)
        check("cli prints malformed rows", "row 5" in proc.stdout and "whole number" in proc.stdout)
        data = json.load(open(out_json, encoding="utf-8"))
        check("json counts exceptions by action type", data["by_action_type"].get("reship_or_refund") == 1 and data["by_action_type"].get("escalate_supervisor") == 1)
        check("json carries duplicate report", len(data["duplicates"]) == 1)
        doc = open(out_html, encoding="utf-8").read()
        check("html report is a blueprint board with plotted zones and routes", "<svg" in doc and "EXCEPTION BOARD" in doc and "escalate_supervisor" in doc and "Space Grotesk" in doc and "UNZONED" in doc)
        check("log file is written", os.path.exists(out_log) and "checked" in open(out_log, encoding="utf-8").read())
        strict = subprocess.run([sys.executable, tool, src, "--strict", "--log", out_log], capture_output=True, text=True)
        check("strict mode exits nonzero on dirty input", strict.returncode == 2)

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1

if __name__ == "__main__":
    raise SystemExit(main())
