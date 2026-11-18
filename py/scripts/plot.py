#!/usr/bin/env python3
"""Generate PDF plots from sweep CSV results.

Reads CSVs from results/sweeps/ and produces 7 PDF figures in figures/:
  - vs_n_latency.pdf, vs_n_messages.pdf
  - vs_byz_latency.pdf, vs_byz_messages.pdf
  - vs_conn_latency.pdf, vs_conn_messages.pdf
  - opt_messages.pdf (combined summary)
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "sweeps"
FIGURES_DIR = Path(__file__).resolve().parent.parent.parent / "figures"

# Shared style
COLORS = {"base": "#2176AE", "optimized": "#F46036"}
MARKERS = {"base": "o", "optimized": "s"}
LABELS = {"base": "Base Dolev", "optimized": "Optimized (MD.1–5)"}


def setup_style():
    plt.rcParams.update({
        "figure.figsize": (5.5, 4),
        "font.size": 10,
        "axes.labelsize": 11,
        "axes.titlesize": 12,
        "legend.fontsize": 9,
        "lines.linewidth": 1.5,
        "lines.markersize": 6,
        "errorbar.capsize": 3,
        "figure.dpi": 150,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.1,
    })


def plot_family(df: pd.DataFrame, x_col: str, x_label: str,
                y_col: str, y_label: str, title: str, out_path: Path):
    """Plot one metric vs one parameter, with base and optimized lines."""
    fig, ax = plt.subplots()

    for variant in ["base", "optimized"]:
        sub = df[df["variant"] == variant]
        if sub.empty:
            continue

        grouped = sub.groupby(x_col)[y_col]
        means = grouped.mean()
        stds = grouped.std().fillna(0)

        ax.errorbar(
            means.index, means.values, yerr=stds.values,
            label=LABELS.get(variant, variant),
            color=COLORS.get(variant, "gray"),
            marker=MARKERS.get(variant, "o"),
            capsize=3,
        )

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)

    fig.savefig(out_path, format="pdf")
    plt.close(fig)
    print(f"  → {out_path}")


def plot_vs_n(results_dir: Path, figures_dir: Path):
    csv_path = results_dir / "vs_n.csv"
    if not csv_path.exists():
        print(f"  SKIP: {csv_path} not found")
        return

    df = pd.read_csv(csv_path)

    plot_family(df, "N", "Number of processes $N$",
                "avg_latency", "Latency [s]",
                "Delivery latency vs. number of processes",
                figures_dir / "vs_n_latency.pdf")

    plot_family(df, "N", "Number of processes $N$",
                "total_messages", "Messages sent",
                "Message complexity vs. number of processes",
                figures_dir / "vs_n_messages.pdf")


def plot_vs_byz(results_dir: Path, figures_dir: Path):
    csv_path = results_dir / "vs_byz.csv"
    if not csv_path.exists():
        print(f"  SKIP: {csv_path} not found")
        return

    df = pd.read_csv(csv_path)

    plot_family(df, "b", "Number of Byzantine nodes $b$",
                "avg_latency", "Latency [s]",
                "Delivery latency vs. Byzantine node count",
                figures_dir / "vs_byz_latency.pdf")

    plot_family(df, "b", "Number of Byzantine nodes $b$",
                "total_messages", "Messages sent",
                "Message complexity vs. Byzantine node count",
                figures_dir / "vs_byz_messages.pdf")


def plot_vs_conn(results_dir: Path, figures_dir: Path):
    csv_path = results_dir / "vs_conn.csv"
    if not csv_path.exists():
        print(f"  SKIP: {csv_path} not found")
        return

    df = pd.read_csv(csv_path)

    plot_family(df, "k", "Network connectivity $k$",
                "avg_latency", "Latency [s]",
                "Delivery latency vs. network connectivity",
                figures_dir / "vs_conn_latency.pdf")

    plot_family(df, "k", "Network connectivity $k$",
                "total_messages", "Messages sent",
                "Message complexity vs. network connectivity",
                figures_dir / "vs_conn_messages.pdf")


def plot_opt_summary(results_dir: Path, figures_dir: Path):
    """Combined bar chart: base vs optimized messages across all families."""
    families = ["vs_n", "vs_byz", "vs_conn"]
    all_data = []
    for fam in families:
        csv_path = results_dir / f"{fam}.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            df["family"] = fam
            all_data.append(df)

    if not all_data:
        print("  SKIP: no CSV data for opt_messages summary")
        return

    df = pd.concat(all_data, ignore_index=True)

    fig, ax = plt.subplots()
    base_mean = df[df["variant"] == "base"]["total_messages"].mean()
    opt_mean = df[df["variant"] == "optimized"]["total_messages"].mean()
    base_std = df[df["variant"] == "base"]["total_messages"].std()
    opt_std = df[df["variant"] == "optimized"]["total_messages"].std()

    bars = ax.bar(
        ["Base Dolev", "Optimized (MD.1–5)"],
        [base_mean, opt_mean],
        yerr=[base_std, opt_std],
        color=[COLORS["base"], COLORS["optimized"]],
        capsize=5, width=0.5,
    )

    # Add percentage label
    if base_mean > 0:
        pct = (1 - opt_mean / base_mean) * 100
        ax.annotate(f"−{pct:.0f}%", xy=(1, opt_mean), xytext=(1.25, (base_mean + opt_mean) / 2),
                    fontsize=11, fontweight="bold", ha="left",
                    arrowprops=dict(arrowstyle="->", color="gray"))

    ax.set_ylabel("Messages sent (mean across all sweeps)")
    ax.set_title("Effect of MD.1–5 optimizations")
    ax.grid(True, alpha=0.3, axis="y")

    fig.savefig(figures_dir / "opt_messages.pdf", format="pdf")
    plt.close(fig)
    print(f"  → {figures_dir / 'opt_messages.pdf'}")


def main():
    parser = argparse.ArgumentParser(description="Generate plots from sweep results")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--figures-dir", type=Path, default=FIGURES_DIR)
    args = parser.parse_args()

    args.figures_dir.mkdir(parents=True, exist_ok=True)
    setup_style()

    print("Generating plots...")
    plot_vs_n(args.results_dir, args.figures_dir)
    plot_vs_byz(args.results_dir, args.figures_dir)
    plot_vs_conn(args.results_dir, args.figures_dir)
    plot_opt_summary(args.results_dir, args.figures_dir)
    print("Done.")


if __name__ == "__main__":
    main()
