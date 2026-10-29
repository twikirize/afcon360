#!/usr/bin/env python
"""Benchmark hosted routing engines on Uganda / East Africa trips.

Usage examples:
    python scripts/routing_benchmark.py
    python scripts/routing_benchmark.py --profile motorcycle
    python scripts/routing_benchmark.py --providers osrm,geoapify \
        --osrm-url https://router.project-osrm.org
    python scripts/routing_benchmark.py --providers valhalla \
        --valhalla-url https://valhalla1.openstreetmap.de

The script never prints provider credentials and never mutates application
data. Results are written under var/routing-lab/ (gitignored).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import statistics
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from app.geo.config import load_geo_config
from app.geo.interfaces import GeoPoint
from app.geo.services import (build_routing_provider,
                              straight_line_distance_m)

PROVIDERS = ("valhalla", "osrm", "geoapify", "graphhopper", "ors",
             "google")


def _load_pairs(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    pairs = payload.get("pairs") if isinstance(payload, dict) else payload
    if not isinstance(pairs, list) or not pairs:
        raise ValueError(f"No routing pairs found in {path}")
    return pairs


def _apply_overrides(config, args):
    if args.valhalla_url:
        config = replace(
            config,
            valhalla=replace(config.valhalla, base_url=args.valhalla_url,
                             enabled=True),
        )
    if args.osrm_url:
        config = replace(
            config,
            osrm=replace(config.osrm, base_url=args.osrm_url, enabled=True),
        )
    return config


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1,
                max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def _run(args) -> int:
    load_dotenv(ROOT / args.env_file, override=False)
    config = _apply_overrides(load_geo_config(), args)
    pairs_path = Path(args.pairs)
    if not pairs_path.is_absolute():
        pairs_path = ROOT / pairs_path
    pairs = _load_pairs(pairs_path)
    if args.limit:
        pairs = pairs[:args.limit]
    requested = [name.strip().lower()
                 for name in args.providers.split(",") if name.strip()]
    unknown = [name for name in requested if name not in PROVIDERS]
    if unknown:
        print(f"Unknown provider(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    adapters = {}
    for name in requested:
        adapters[name] = build_routing_provider(name, config, force=True)

    results: list[dict] = []
    for pair in pairs:
        origin_data = pair["origin"]
        destination_data = pair["destination"]
        origin = GeoPoint(float(origin_data["lat"]),
                          float(origin_data["lon"]))
        destination = GeoPoint(float(destination_data["lat"]),
                               float(destination_data["lon"]))
        profile = args.profile or pair.get("profile") or "auto"
        straight_m = straight_line_distance_m(origin, destination)
        for name in requested:
            adapter = adapters.get(name)
            if adapter is None:
                results.append({
                    "pair_id": pair.get("id", ""),
                    "origin": origin_data.get("name", ""),
                    "destination": destination_data.get("name", ""),
                    "profile": profile,
                    "provider": name,
                    "resolved": False,
                    "distance_km": None,
                    "duration_min": None,
                    "detour_ratio": None,
                    "latency_ms": None,
                    "error": "not_configured",
                })
                continue
            if not adapter.is_available():
                results.append({
                    "pair_id": pair.get("id", ""),
                    "origin": origin_data.get("name", ""),
                    "destination": destination_data.get("name", ""),
                    "profile": profile,
                    "provider": name,
                    "resolved": False,
                    "distance_km": None,
                    "duration_min": None,
                    "detour_ratio": None,
                    "latency_ms": None,
                    "error": "not_available",
                })
                continue
            started = time.perf_counter()
            route = adapter.route(origin, destination, profile=profile)
            latency_ms = (time.perf_counter() - started) * 1000.0
            resolved = bool(route.resolved)
            distance_km = (route.distance_m / 1000.0) if resolved else None
            duration_min = (route.duration_s / 60.0) if resolved else None
            detour_ratio = None
            if resolved and straight_m > 0:
                detour_ratio = route.distance_m / straight_m
            results.append({
                "pair_id": pair.get("id", ""),
                "origin": origin_data.get("name", ""),
                "destination": destination_data.get("name", ""),
                "profile": profile,
                "provider": name,
                "resolved": resolved,
                "distance_km": (round(distance_km, 2)
                                if distance_km is not None else None),
                "duration_min": (round(duration_min, 1)
                                 if duration_min is not None else None),
                "straight_line_km": round(straight_m / 1000.0, 2),
                "detour_ratio": (round(detour_ratio, 3)
                                 if detour_ratio is not None else None),
                "latency_ms": round(latency_ms, 1),
                "error": None if resolved else "unresolved",
            })
            if args.sleep > 0:
                time.sleep(args.sleep)

    summary = {}
    for name in requested:
        rows = [row for row in results if row["provider"] == name]
        ok = [row for row in rows if row["resolved"]]
        detours = [row["detour_ratio"] for row in ok
                   if row["detour_ratio"] is not None]
        latencies = [row["latency_ms"] for row in rows
                     if row["latency_ms"] is not None]
        summary[name] = {
            "requests": len(rows),
            "resolved": len(ok),
            "failed": len(rows) - len(ok),
            "mean_detour_ratio": (round(statistics.mean(detours), 3)
                                  if detours else None),
            "median_detour_ratio": (round(statistics.median(detours), 3)
                                    if detours else None),
            "p50_latency_ms": (round(statistics.median(latencies), 1)
                               if latencies else None),
            "p95_latency_ms": (round(_percentile(latencies, 0.95), 1)
                               if latencies else None),
        }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.out_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"routing-benchmark-{stamp}.json"
    csv_path = output_dir / f"routing-benchmark-{stamp}.csv"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile_override": args.profile,
        "pairs_file": str(pairs_path),
        "results": results,
        "summary": summary,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    fieldnames = [
        "pair_id", "origin", "destination", "profile", "provider",
        "resolved", "distance_km", "duration_min", "straight_line_km",
        "detour_ratio", "latency_ms", "error",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Routing benchmark | pairs={len(pairs)} | "
          f"profile={args.profile or 'per-pair'}")
    print(f"{'provider':<10} {'ok':>4} {'fail':>5} "
          f"{'median_detour':>14} {'p50_ms':>9} {'p95_ms':>9}")
    for name in requested:
        item = summary[name]
        detour = item["median_detour_ratio"]
        detour_text = f"{detour:.3f}" if detour is not None else "-"
        p50 = item["p50_latency_ms"]
        p95 = item["p95_latency_ms"]
        p50_text = f"{p50:.0f}" if p50 is not None else "-"
        p95_text = f"{p95:.0f}" if p95 is not None else "-"
        print(f"{name:<10} {item['resolved']:>4} {item['failed']:>5} "
              f"{detour_text:>14} {p50_text:>9} {p95_text:>9}")
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark hosted routing engines on AFCON360 trips.")
    parser.add_argument("--pairs", default="scripts/routing_pairs_uganda.json")
    parser.add_argument(
        "--providers", default="valhalla,osrm,geoapify",
        help="comma list: valhalla,osrm,geoapify,graphhopper,ors,google")
    parser.add_argument("--profile", default=None,
                        choices=["auto", "motorcycle", "pedestrian",
                                 "bicycle", "scooter", "truck"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=0.4)
    parser.add_argument("--out-dir", default="var/routing-lab")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--valhalla-url", default=None)
    parser.add_argument("--osrm-url", default=None)
    return _run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
