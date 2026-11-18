#!/usr/bin/env python3
"""Run sweep configurations and collect results into CSV files.

Reads all YAML configs in configs/sweeps/, runs each one R times through
distbench, parses per-node reports, and writes summary CSVs to results/sweeps/.
"""

import argparse
import csv
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs" / "sweeps"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "sweeps"


PY_DIR = Path(__file__).resolve().parent.parent  # py/


def run_config(config_path: Path, timeout: int = 30) -> dict:
    """Run a single config and return aggregated metrics."""
    # config_path is absolute; make it relative to py/ for distbench
    try:
        rel_config = config_path.resolve().relative_to(PY_DIR)
    except ValueError:
        rel_config = config_path
    result = subprocess.run(
        [
            str(PY_DIR / ".venv" / "bin" / "distbench"),
            "-c", str(rel_config),
            "-a", "dolev",
            "-t", str(timeout),
            "-v",
        ],
        capture_output=True,
        text=True,
        cwd=str(PY_DIR),
        timeout=timeout + 15,
    )
    output = result.stdout + result.stderr

    reports = {}
    for line in output.split("\n"):
        m = re.search(r"Algorithm report for (\w+): (\{.*\})", line)
        if m:
            node_id = m.group(1)
            try:
                report = eval(m.group(2))  # noqa: S307 — trusted output
                reports[node_id] = report
            except Exception:
                pass

    # Aggregate
    total_messages = 0
    total_delivered = 0
    latencies = []
    correct_count = 0

    for node_id, report in reports.items():
        details = report.get("details", {})
        is_byz = details.get("byzantine") == "True"

        msgs = int(details.get("messages_sent", "0"))
        delivered = int(details.get("delivered_count", "0"))
        total_messages += msgs

        if not is_byz:
            correct_count += 1
            total_delivered += delivered
            # Parse avg_latency_s
            lat_str = details.get("avg_latency_s", "0.0")
            try:
                lat = float(lat_str)
                if lat > 0:
                    latencies.append(lat)
            except ValueError:
                pass

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    return {
        "total_messages": total_messages,
        "total_delivered": total_delivered,
        "avg_latency": avg_latency,
        "correct_nodes": correct_count,
        "num_reports": len(reports),
    }


def parse_config_name(name: str) -> dict:
    """Extract parameters from config filename."""
    params = {}
    # e.g., sweep_vs_n_base_N10_f1_k3.yaml
    if "_base_" in name:
        params["variant"] = "base"
    elif "_opt_" in name:
        params["variant"] = "optimized"

    for part in name.replace(".yaml", "").split("_"):
        if part.startswith("N") and part[1:].isdigit():
            params["N"] = int(part[1:])
        elif part.startswith("f") and part[1:].isdigit():
            params["f"] = int(part[1:])
        elif part.startswith("k") and part[1:].isdigit():
            params["k"] = int(part[1:])
        elif part.startswith("b") and part[1:].isdigit():
            params["b"] = int(part[1:])

    return params


def run_sweep_family(family: str, configs: list[Path], runs: int, timeout: int, results_dir: Path):
    """Run all configs for a family, write CSV."""
    csv_path = results_dir / f"{family}.csv"
    fieldnames = ["N", "f", "k", "b", "variant", "run",
                  "total_messages", "total_delivered", "avg_latency",
                  "correct_nodes", "num_reports"]

    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()

        for config_path in sorted(configs):
            params = parse_config_name(config_path.name)
            label = config_path.stem
            print(f"  Running {label} ({runs} runs)...", end=" ", flush=True)

            for run_idx in range(runs):
                try:
                    metrics = run_config(config_path, timeout=timeout)
                    row = {**params, "run": run_idx, **metrics}
                    # Fill missing params with defaults
                    row.setdefault("N", 10)
                    row.setdefault("f", 1)
                    row.setdefault("k", 3)
                    row.setdefault("b", 0)
                    row.setdefault("variant", "base")
                    writer.writerow(row)
                except subprocess.TimeoutExpired:
                    print(f"TIMEOUT (run {run_idx})", end=" ")
                except Exception as e:
                    print(f"ERROR: {e}", end=" ")

            print("done")

    print(f"  → {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Run Dolev sweep experiments")
    parser.add_argument("--runs", type=int, default=3, help="Repetitions per config")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per run (seconds)")
    parser.add_argument("--configs-dir", type=Path, default=CONFIGS_DIR)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--family", type=str, default=None,
                        help="Run only one family: vs_n, vs_byz, vs_conn")
    args = parser.parse_args()

    args.results_dir.mkdir(parents=True, exist_ok=True)

    if not args.configs_dir.exists():
        print(f"No configs dir: {args.configs_dir}. Run gen_configs.py first.")
        sys.exit(1)

    all_configs = list(args.configs_dir.glob("sweep_*.yaml"))
    if not all_configs:
        print(f"No sweep configs found in {args.configs_dir}. Run gen_configs.py first.")
        sys.exit(1)

    families = {}
    for cfg in all_configs:
        # Extract family from name: sweep_vs_n_..., sweep_vs_byz_..., sweep_vs_conn_...
        parts = cfg.stem.split("_")
        # family = vs_n, vs_byz, vs_conn
        if len(parts) >= 3:
            family = f"{parts[1]}_{parts[2]}"
        else:
            family = "unknown"
        families.setdefault(family, []).append(cfg)

    for family, configs in sorted(families.items()):
        if args.family and args.family != family:
            continue
        print(f"\n=== Family: {family} ({len(configs)} configs × {args.runs} runs) ===")
        run_sweep_family(family, configs, args.runs, args.timeout, args.results_dir)

    print("\nAll sweeps complete.")


if __name__ == "__main__":
    main()
