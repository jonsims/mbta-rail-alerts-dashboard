#!/usr/bin/env python3
"""Preprocess MBTA 2025 alert CSVs into compact JSON for the dashboard.
Focused on rail-only: Subway, Light Rail (Green Line), and Commuter Rail."""

import csv
import json
import os
import urllib.request
from collections import defaultdict
from datetime import datetime

DATA_DIR = "Alerts_2025"
OUTPUT = "alerts_data.json"

# Only include rail route types
RAIL_ROUTE_TYPES = {"0", "1", "2"}  # 0=Light Rail, 1=Subway, 2=Commuter Rail

ROUTE_TYPE_NAMES = {
    "0": "Green Line",
    "1": "Subway",
    "2": "Commuter Rail",
}

DAYS_PER_MONTH_2025 = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# MBTA official colors
ROUTE_COLORS = {
    "Red": "#DA291C", "Orange": "#ED8B00", "Blue": "#003DA5",
    "Green-B": "#00843D", "Green-C": "#00843D", "Green-D": "#00843D", "Green-E": "#00843D",
    "Mattapan": "#DA291C",
    "CR-Worcester": "#80276C", "CR-Fitchburg": "#80276C", "CR-Franklin": "#80276C",
    "CR-Providence": "#80276C", "CR-Newburyport": "#80276C", "CR-NewBedford": "#80276C",
    "CR-Haverhill": "#80276C", "CR-Lowell": "#80276C", "CR-Kingston": "#80276C",
    "CR-Greenbush": "#80276C", "CR-Fairmount": "#80276C", "CR-Needham": "#80276C",
    "CR-Middleborough": "#80276C", "CR-Foxboro": "#80276C",
}

ROUTE_DISPLAY_NAMES = {
    "Red": "Red Line", "Orange": "Orange Line", "Blue": "Blue Line",
    "Green-B": "Green Line B", "Green-C": "Green Line C",
    "Green-D": "Green Line D", "Green-E": "Green Line E",
    "Mattapan": "Mattapan Trolley",
    "CR-Worcester": "Worcester Line", "CR-Fitchburg": "Fitchburg Line",
    "CR-Franklin": "Franklin/Foxboro Line", "CR-Providence": "Providence/Stoughton Line",
    "CR-Newburyport": "Newburyport/Rockport Line", "CR-NewBedford": "New Bedford Line",
    "CR-Haverhill": "Haverhill Line", "CR-Lowell": "Lowell Line",
    "CR-Kingston": "Kingston Line", "CR-Greenbush": "Greenbush Line",
    "CR-Fairmount": "Fairmount Line", "CR-Needham": "Needham Line",
    "CR-Middleborough": "Middleborough Line", "CR-Foxboro": "Foxboro Line",
}

# cause_detail → display name (preferred over generic cause field)
CAUSE_DETAIL_DISPLAY = {
    "DISABLED_TRAIN": "Disabled Train",
    "SIGNAL_PROBLEM": "Signal Problem",
    "SIGNAL_ISSUE": "Signal Problem",
    "MAINTENANCE": "Maintenance",
    "POLICE_ACTION": "Police Activity",
    "POLICE_ACTIVITY": "Police Activity",
    "MEDICAL_EMERGENCY": "Medical Emergency",
    "SWITCH_PROBLEM": "Switch Problem",
    "POWER_PROBLEM": "Power Problem",
    "ACCIDENT": "Accident",
    "FIRE_DEPARTMENT_ACTIVITY": "Fire Dept Activity",
    "TRACK_PROBLEM": "Track Problem",
    "SINGLE_TRACKING": "Single Tracking",
    "TRACK_WORK": "Track Work",
    "CONSTRUCTION": "Construction",
    "SNOW": "Weather",
    "SLIPPERY_RAIL": "Weather",
    "WEATHER": "Weather",
    "FLOODING": "Weather",
    "TRAFFIC": "Traffic",
    "FIRE": "Fire",
    "HEAVY_RIDERSHIP": "Heavy Ridership",
    "SPECIAL_EVENT": "Special Event",
    "HOLIDAY": "Special Event",
    "MECHANICAL_ISSUE": "Mechanical Issue",
    "SPEED_RESTRICTION": "Speed Restriction",
    "UNKNOWN_CAUSE": "Unknown",
}

# Fallback: generic cause field → display name
CAUSE_DISPLAY = {
    "CONSTRUCTION": "Construction", "MAINTENANCE": "Maintenance",
    "UNKNOWN_CAUSE": "Unknown", "OTHER_CAUSE": "Other",
    "TECHNICAL_PROBLEM": "Technical Problem", "POLICE_ACTIVITY": "Police Activity",
    "ACCIDENT": "Accident", "WEATHER": "Weather",
    "MEDICAL_EMERGENCY": "Medical Emergency", "STRIKE": "Strike",
    "DEMONSTRATION": "Demonstration", "FIRE": "Fire", "FLOOD": "Weather",
    "POWER_PROBLEM": "Power Problem", "SPECIAL_EVENT": "Special Event", "TRAFFIC": "Traffic",
}

# effect_detail → display name (preferred over generic effect field)
EFFECT_DETAIL_DISPLAY = {
    "DELAY": "Delay",
    "TRACK_CHANGE": "Track Change",
    "CANCELLATION": "Cancellation",
    "SERVICE_CHANGE": "Service Change",
    "SHUTTLE": "Shuttle",
    "ESCALATOR_CLOSURE": "Escalator Closure",
    "ELEVATOR_CLOSURE": "Elevator Closure",
    "SUSPENSION": "Suspension",
    "SCHEDULE_CHANGE": "Schedule Change",
    "STATION_ISSUE": "Station Issue",
    "STATION_CLOSURE": "Station Closure",
    "EXTRA_SERVICE": "Extra Service",
}

# Fallback: generic effect field → display name
EFFECT_DISPLAY = {
    "DETOUR": "Detour", "ACCESSIBILITY_ISSUE": "Accessibility Issue",
    "OTHER_EFFECT": "Other", "STOP_MOVED": "Stop Moved",
    "UNKNOWN_EFFECT": "Unknown", "SIGNIFICANT_DELAYS": "Significant Delays",
    "NO_SERVICE": "No Service", "MODIFIED_SERVICE": "Modified Service",
    "ADDITIONAL_SERVICE": "Additional Service", "REDUCED_SERVICE": "Reduced Service",
    "SHUTTLE": "Shuttle", "STOP_CLOSURE": "Stop Closure",
    "STATION_CLOSURE": "Station Closure", "DELAY": "Delay",
    "SUSPENSION": "Suspension", "SERVICE_CHANGE": "Service Change",
    "SNOW_ROUTE": "Snow Route", "TRACK_CHANGE": "Track Change",
    "SCHEDULE_CHANGE": "Schedule Change", "CANCELLATION": "Cancellation",
    "EXTRA_SERVICE": "Extra Service", "STATION_ISSUE": "Station Issue",
    "BIKE_ISSUE": "Bike Issue", "PARKING_ISSUE": "Parking Issue",
    "DOCK_ISSUE": "Dock Issue", "ELEVATOR_CLOSURE": "Elevator Closure",
    "ESCALATOR_CLOSURE": "Escalator Closure", "POLICY_CHANGE": "Policy Change",
    "FARE_CHANGE": "Fare Change",
}


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def display_cause(cause, cause_detail=""):
    """Prefer cause_detail for richer categorization; fall back to cause."""
    # Try detail field first (unless it's just UNKNOWN_CAUSE echoed back)
    if cause_detail and cause_detail != "UNKNOWN_CAUSE":
        if cause_detail in CAUSE_DETAIL_DISPLAY:
            return CAUSE_DETAIL_DISPLAY[cause_detail]
    # Fall back to generic cause
    return CAUSE_DISPLAY.get(cause, cause.replace("_", " ").title() if cause else "Unknown")


def display_effect(effect, effect_detail=""):
    """Prefer effect_detail for richer categorization; fall back to effect."""
    if effect_detail and effect_detail in EFFECT_DETAIL_DISPLAY:
        return EFFECT_DETAIL_DISPLAY[effect_detail]
    return EFFECT_DISPLAY.get(effect, effect.replace("_", " ").title() if effect else "Unknown")


# ── Google Encoded Polyline Decoder ──
def decode_polyline(encoded):
    """Decode a Google encoded polyline string into list of [lng, lat] (GeoJSON order)."""
    coords = []
    index = 0
    lat = 0
    lng = 0
    while index < len(encoded):
        # Decode latitude
        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lat += (~(result >> 1) if (result & 1) else (result >> 1))

        # Decode longitude
        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lng += (~(result >> 1) if (result & 1) else (result >> 1))

        coords.append([lng / 1e5, lat / 1e5])  # GeoJSON: [lng, lat]
    return coords


def fetch_route_shapes(route_ids):
    """Fetch canonical route shapes from the MBTA V3 API and return GeoJSON."""
    route_list = ",".join(route_ids)
    # direction_id=0 gives us one direction per pattern (avoid duplicates)
    url = (
        f"https://api-v3.mbta.com/route_patterns"
        f"?filter[route]={route_list}"
        f"&filter[canonical]=true"
        f"&filter[direction_id]=0"
        f"&include=representative_trip.shape"
        f"&fields[shape]=polyline"
    )

    print(f"  Fetching shapes from MBTA API...")
    print(f"  URL: {url[:100]}...")

    req = urllib.request.Request(url, headers={"Accept": "application/vnd.api+json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())

    # Build shape lookup: shape_id -> polyline
    shape_lookup = {}
    for item in data.get("included", []):
        if item["type"] == "shape":
            shape_lookup[item["id"]] = item["attributes"]["polyline"]

    # Build trip -> shape lookup
    trip_shape = {}
    for item in data.get("included", []):
        if item["type"] == "trip":
            shape_ref = item.get("relationships", {}).get("shape", {}).get("data")
            if shape_ref:
                trip_shape[item["id"]] = shape_ref["id"]

    # Map route_patterns -> route_id -> list of polylines
    route_polylines = defaultdict(list)
    for rp in data.get("data", []):
        route_id = rp["relationships"]["route"]["data"]["id"]
        trip_ref = rp.get("relationships", {}).get("representative_trip", {}).get("data")
        if trip_ref and trip_ref["id"] in trip_shape:
            shape_id = trip_shape[trip_ref["id"]]
            if shape_id in shape_lookup:
                coords = decode_polyline(shape_lookup[shape_id])
                if coords:
                    route_polylines[route_id].append(coords)

    # Build GeoJSON FeatureCollection
    features = []
    for route_id, coord_lists in route_polylines.items():
        rt_name = ROUTE_TYPE_NAMES.get("1", "Subway")
        if route_id.startswith("CR-"):
            rt_name = "Commuter Rail"
        elif route_id.startswith("Green-") or route_id == "Mattapan":
            rt_name = "Green Line"

        if len(coord_lists) == 1:
            geometry = {"type": "LineString", "coordinates": coord_lists[0]}
        else:
            geometry = {"type": "MultiLineString", "coordinates": coord_lists}

        features.append({
            "type": "Feature",
            "properties": {
                "routeId": route_id,
                "color": ROUTE_COLORS.get(route_id, "#80276C"),
                "displayName": ROUTE_DISPLAY_NAMES.get(route_id, route_id),
                "routeType": rt_name,
            },
            "geometry": geometry,
        })

    print(f"  Got shapes for {len(features)} routes: {sorted(route_polylines.keys())}")
    return {"type": "FeatureCollection", "features": features}


def main():
    print("Reading CSV files (rail-only)...")
    alerts = {}
    records = []

    csv_files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".csv"))
    skipped = 0

    for fname in csv_files:
        print(f"  Processing {fname}...")
        filepath = os.path.join(DATA_DIR, fname)
        with open(filepath, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rt = row.get("route_type", "")
                if rt not in RAIL_ROUTE_TYPES:
                    skipped += 1
                    continue

                aid = row["alert_id"]
                mod_dt = row["last_modified_dt"] or ""
                if aid not in alerts or mod_dt > alerts[aid]["last_modified_dt"]:
                    alerts[aid] = row

                start_dt = parse_dt(row.get("active_period_start_dt", ""))
                end_dt = parse_dt(row.get("active_period_end_dt", ""))
                if start_dt:
                    rt_name = ROUTE_TYPE_NAMES.get(rt, "Other")
                    duration_hours = None
                    if end_dt and end_dt > start_dt:
                        duration_hours = (end_dt - start_dt).total_seconds() / 3600
                    records.append((
                        aid,
                        start_dt.strftime("%Y-%m"),
                        start_dt.weekday(),
                        start_dt.hour,
                        rt_name,
                        display_cause(row.get("cause", ""), row.get("cause_detail", "")),
                        display_effect(row.get("effect", ""), row.get("effect_detail", "")),
                        row.get("severity_level", "") or "INFO",
                        row.get("route_id", ""),
                        row.get("active_period_start_date", ""),
                        duration_hours,
                    ))

    print(f"  Unique rail alerts: {len(alerts)}")
    print(f"  Rail records: {len(records)}, skipped non-rail: {skipped}")

    # ── Aggregations ──
    print("Building aggregations...")
    months = sorted(set(r[1] for r in records))
    all_rt_names = sorted(set(r[4] for r in records))

    g_monthly_cause = defaultdict(lambda: defaultdict(int))
    g_monthly_sev = defaultdict(lambda: defaultdict(int))
    g_monthly_rt = defaultdict(lambda: defaultdict(int))
    g_monthly_effect = defaultdict(lambda: defaultdict(int))
    g_cause_totals = defaultdict(int)
    g_effect_totals = defaultdict(int)
    g_sev_totals = defaultdict(int)
    g_heatmap = defaultdict(int)

    rt_monthly_cause = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    rt_monthly_sev = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    rt_monthly_effect = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    rt_cause_totals = defaultdict(lambda: defaultdict(int))
    rt_effect_totals = defaultdict(lambda: defaultdict(int))
    rt_heatmap = defaultdict(lambda: defaultdict(int))

    route_stats = defaultdict(lambda: {
        "count": 0, "causes": defaultdict(int), "effects": defaultdict(int),
        "severities": defaultdict(int), "route_type": "", "months": defaultdict(int),
        "durations": [],
        "monthly_sev": defaultdict(lambda: defaultdict(int)),  # month -> sev -> count
    })

    # Duration tracking
    g_durations = []
    rt_durations = defaultdict(list)

    seen_global = set()
    seen_per_rt = set()
    seen_heatmap = set()
    seen_heatmap_rt = set()
    seen_route = set()

    for aid, month, dow, hour, rt_name, cause, effect, sev, route_id, start_date, duration_hours in records:
        global_key = (aid, month)
        rt_key = (aid, month, rt_name)

        if global_key not in seen_global:
            seen_global.add(global_key)
            g_monthly_cause[month][cause] += 1
            g_monthly_sev[month][sev] += 1
            g_monthly_rt[month][rt_name] += 1
            g_monthly_effect[month][effect] += 1
            g_cause_totals[cause] += 1
            g_effect_totals[effect] += 1
            g_sev_totals[sev] += 1
            if duration_hours is not None and duration_hours < 720:  # Cap at 30 days
                g_durations.append(duration_hours)

        if rt_key not in seen_per_rt:
            seen_per_rt.add(rt_key)
            rt_monthly_cause[rt_name][month][cause] += 1
            rt_monthly_sev[rt_name][month][sev] += 1
            rt_monthly_effect[rt_name][month][effect] += 1
            rt_cause_totals[rt_name][cause] += 1
            rt_effect_totals[rt_name][effect] += 1
            if duration_hours is not None and duration_hours < 720:
                rt_durations[rt_name].append(duration_hours)

        if start_date:
            hm_key = (aid, start_date)
            hm_rt_key = (aid, start_date, rt_name)
            if hm_key not in seen_heatmap:
                seen_heatmap.add(hm_key)
                g_heatmap[(dow, hour)] += 1
            if hm_rt_key not in seen_heatmap_rt:
                seen_heatmap_rt.add(hm_rt_key)
                rt_heatmap[rt_name][(dow, hour)] += 1

        if route_id:
            route_key = (aid, month, route_id)
            if route_key not in seen_route:
                seen_route.add(route_key)
                rs = route_stats[route_id]
                rs["count"] += 1
                rs["causes"][cause] += 1
                rs["effects"][effect] += 1
                rs["severities"][sev] += 1
                rs["months"][month] += 1
                rs["monthly_sev"][month][sev] += 1
                if rt_name:
                    rs["route_type"] = rt_name
                if duration_hours is not None and duration_hours < 720:
                    rs["durations"].append(duration_hours)

    # ── Duration stats helper ──
    def duration_stats(durations_list):
        if not durations_list:
            return {"median": 0, "mean": 0, "p90": 0, "count": 0}
        s = sorted(durations_list)
        n = len(s)
        return {
            "median": round((s[(n - 1) // 2] + s[n // 2]) / 2, 1),
            "mean": round(sum(s) / n, 1),
            "p90": round(s[int(n * 0.9)], 1),
            "count": n,
        }

    # ── Build output ──
    print("Building output JSON...")

    top_causes = [c for c, _ in sorted(g_cause_totals.items(), key=lambda x: -x[1])]
    top_effects = [e for e, _ in sorted(g_effect_totals.items(), key=lambda x: -x[1])]

    def build_series(monthly_dict, categories):
        return {cat: [monthly_dict[m].get(cat, 0) for m in months] for cat in categories}

    def build_heatmap(hm):
        return [[hm.get((d, h), 0) for h in range(24)] for d in range(7)]

    by_route_type = {}
    for rt in all_rt_names:
        rt_causes = [c for c, _ in sorted(rt_cause_totals[rt].items(), key=lambda x: -x[1])]
        rt_effects = [e for e, _ in sorted(rt_effect_totals[rt].items(), key=lambda x: -x[1])]
        by_route_type[rt] = {
            "causes": rt_causes,
            "effects": rt_effects,
            "causeTotals": dict(rt_cause_totals[rt]),
            "effectTotals": dict(rt_effect_totals[rt]),
            "monthlyCause": build_series(rt_monthly_cause[rt], rt_causes),
            "monthlySeverity": build_series(rt_monthly_sev[rt], ["INFO", "WARNING", "SEVERE"]),
            "monthlyEffect": build_series(rt_monthly_effect[rt], rt_effects),
            "heatmap": build_heatmap(rt_heatmap[rt]),
            "duration": duration_stats(rt_durations[rt]),
        }

    sev_weights = {"INFO": 1, "WARNING": 2, "SEVERE": 3}
    route_table = []
    for rid, rs in sorted(route_stats.items(), key=lambda x: -x[1]["count"]):
        total = rs["count"]
        top_cause = max(rs["causes"].items(), key=lambda x: x[1])[0] if rs["causes"] else ""
        top_effect = max(rs["effects"].items(), key=lambda x: x[1])[0] if rs["effects"] else ""
        avg_sev = sum(sev_weights.get(k, 1) * v for k, v in rs["severities"].items()) / max(total, 1)
        route_table.append({
            "id": rid,
            "type": rs["route_type"] or "Unknown",
            "count": total,
            "avgSev": round(avg_sev, 2),
            "topCause": top_cause,
            "topEffect": top_effect,
            "severe": rs["severities"].get("SEVERE", 0),
            "warning": rs["severities"].get("WARNING", 0),
            "info": rs["severities"].get("INFO", 0),
            "months": {m: rs["months"].get(m, 0) for m in months},
            "monthlySev": {
                sev_level: [rs["monthly_sev"][m].get(sev_level, 0) for m in months]
                for sev_level in ["SEVERE", "WARNING", "INFO"]
            },
            "color": ROUTE_COLORS.get(rid, "#80276C"),
            "displayName": ROUTE_DISPLAY_NAMES.get(rid, rid),
            "duration": duration_stats(rs["durations"]),
        })

    # ── Fetch route shapes from MBTA API ──
    print("Fetching route shapes...")
    known_route_ids = [r["id"] for r in route_table if r["id"] in ROUTE_COLORS]
    try:
        route_shapes = fetch_route_shapes(known_route_ids)
    except Exception as e:
        print(f"  WARNING: Could not fetch shapes: {e}")
        print(f"  Dashboard will work without map.")
        route_shapes = {"type": "FeatureCollection", "features": []}

    output = {
        "generated": datetime.now().isoformat(),
        "dataRange": {"from": months[0] if months else "", "to": months[-1] if months else ""},
        "summary": {
            "totalAlerts": len(alerts),
            "totalAlertMonths": len(seen_global),
            "topRoute": route_table[0]["id"] if route_table else "",
            "topCause": top_causes[0] if top_causes else "",
        },
        "months": months,
        "daysPerMonth": DAYS_PER_MONTH_2025,
        "causes": top_causes,
        "effects": top_effects,
        "causeTotals": dict(g_cause_totals),
        "effectTotals": dict(g_effect_totals),
        "monthlyCause": build_series(g_monthly_cause, top_causes),
        "monthlySeverity": build_series(g_monthly_sev, ["INFO", "WARNING", "SEVERE"]),
        "monthlyRouteType": build_series(g_monthly_rt, all_rt_names),
        "monthlyEffect": build_series(g_monthly_effect, top_effects),
        "heatmap": build_heatmap(g_heatmap),
        "byRouteType": by_route_type,
        "routeTable": route_table,
        "routeTypeNames": list(ROUTE_TYPE_NAMES.values()),
        "routeShapes": route_shapes,
        "duration": duration_stats(g_durations),
    }

    with open(OUTPUT, "w") as f:
        json.dump(output, f)

    size_mb = os.path.getsize(OUTPUT) / 1024 / 1024
    print(f"Done! Wrote {OUTPUT} ({size_mb:.2f} MB)")
    print(f"  Routes: {len(route_table)}")
    print(f"  Route types: {all_rt_names}")
    print(f"  Map shapes: {len(route_shapes['features'])}")


if __name__ == "__main__":
    main()
