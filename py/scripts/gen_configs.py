#!/usr/bin/env python3
"""Generate sweep YAML configs using Harary graphs H_{k,N}.

Harary graph H_{k,N}:
  - Start with a ring of N nodes.
  - Add chords of jump 2, 3, ..., floor(k/2).
  - If k is odd and N is even, add antipodal chord (jump N/2).
  - Result: a k-connected, k-regular (or near-regular) graph on N nodes.

This produces configs for three sweep families:
  1. vs_n:    varying N with fixed f, k=2f+1, b=0
  2. vs_byz:  varying b (number of passive Byzantine nodes) with fixed N, f, k
  3. vs_conn: varying k (connectivity) with fixed N, f, b=0
"""

import argparse
import sys
from pathlib import Path

import networkx as nx
import yaml


def harary_graph(k: int, n: int) -> dict[str, list[str]]:
    """Build a Harary graph H_{k,n} and return adjacency as {node_id: [neighbour_ids]}."""
    G = nx.hkn_harary_graph(k, n)
    adj: dict[str, list[str]] = {}
    for i in range(n):
        node_id = f"node{i}"
        neighbours = sorted([f"node{j}" for j in G.neighbors(i)], key=lambda x: int(x[4:]))
        adj[node_id] = neighbours

    # Verify connectivity
    conn = nx.node_connectivity(G)
    if conn < k:
        print(f"WARNING: H_{{{k},{n}}} has connectivity {conn}, expected >= {k}", file=sys.stderr)
    return adj


def make_config(
    n: int, f: int, k: int, b: int, optimized: bool,
    delay_min: float = 0.0, delay_max: float = 0.3,
) -> dict:
    """Generate a YAML-serializable config dict."""
    adj = harary_graph(k, n)
    nodes = sorted(adj.keys(), key=lambda x: int(x[4:]))

    config = {}
    # Byzantine nodes are the LAST b nodes (excluding node0 which is the broadcaster)
    byz_set = set(nodes[n - b:]) if b > 0 else set()
    # Make sure node0 is never Byzantine (it's the broadcaster)
    byz_set.discard("node0")

    for node_id in nodes:
        is_byz = node_id in byz_set
        entry = {
            "f": f,
            "optimized": optimized,
            "broadcaster": node_id == "node0" and not is_byz,
            "messages": ["sweep_msg"] if (node_id == "node0" and not is_byz) else [],
            "byzantine": is_byz,
            "byzantine_mode": "passive" if is_byz else "passive",
            "byzantine_target": "",
            "delay_min": delay_min,
            "delay_max": delay_max,
            "neighbours": adj[node_id],
        }
        config[node_id] = entry

    return config


def gen_vs_n(out_dir: Path, f: int = 1, ns: list[int] | None = None):
    """Sweep over N with k=2f+1, b=0."""
    k = 2 * f + 1
    if ns is None:
        ns = [6, 8, 10, 15, 20, 30]
    # Filter: N must be > k for Harary graph to work
    ns = [n for n in ns if n > k]

    for n in ns:
        for opt_label, opt_val in [("base", False), ("opt", True)]:
            cfg = make_config(n, f, k, b=0, optimized=opt_val)
            fname = f"sweep_vs_n_{opt_label}_N{n}_f{f}_k{k}.yaml"
            path = out_dir / fname
            with open(path, "w") as fh:
                yaml.dump(cfg, fh, default_flow_style=False, sort_keys=False)
    print(f"vs_n: generated {len(ns) * 2} configs for N={ns}, f={f}, k={k}")


def gen_vs_byz(out_dir: Path, n: int = 10, f: int = 2, bs: list[int] | None = None):
    """Sweep over b (Byzantine count) with fixed N, f, k=2f+1."""
    k = 2 * f + 1
    if bs is None:
        bs = list(range(0, f + 1))  # 0 to f inclusive
    # Ensure we don't make node0 Byzantine
    bs = [b for b in bs if b < n]

    for b in bs:
        for opt_label, opt_val in [("base", False), ("opt", True)]:
            cfg = make_config(n, f, k, b=b, optimized=opt_val)
            fname = f"sweep_vs_byz_{opt_label}_N{n}_f{f}_k{k}_b{b}.yaml"
            path = out_dir / fname
            with open(path, "w") as fh:
                yaml.dump(cfg, fh, default_flow_style=False, sort_keys=False)
    print(f"vs_byz: generated {len(bs) * 2} configs for b={bs}, N={n}, f={f}, k={k}")


def gen_vs_conn(out_dir: Path, n: int = 10, f: int = 1, ks: list[int] | None = None):
    """Sweep over k (connectivity) with fixed N, f, b=0."""
    if ks is None:
        # k must be >= 2f+1 and < N
        k_min = 2 * f + 1
        ks = [k for k in range(k_min, min(n, k_min + 6)) if k < n]

    for k in ks:
        for opt_label, opt_val in [("base", False), ("opt", True)]:
            cfg = make_config(n, f, k, b=0, optimized=opt_val)
            fname = f"sweep_vs_conn_{opt_label}_N{n}_f{f}_k{k}.yaml"
            path = out_dir / fname
            with open(path, "w") as fh:
                yaml.dump(cfg, fh, default_flow_style=False, sort_keys=False)
    print(f"vs_conn: generated {len(ks) * 2} configs for k={ks}, N={n}, f={f}")


def main():
    parser = argparse.ArgumentParser(description="Generate sweep configs for Dolev experiments")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "configs" / "sweeps")
    parser.add_argument("--f", type=int, default=1, dest="fault_bound", help="Max Byzantine faults f")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    f = args.fault_bound
    gen_vs_n(args.out, f=f, ns=[6, 8, 10, 15, 20, 30])
    gen_vs_byz(args.out, n=10, f=2, bs=[0, 1, 2])
    gen_vs_conn(args.out, n=10, f=f, ks=[3, 4, 5, 6, 7, 8])

    print(f"\nAll configs written to {args.out}")


if __name__ == "__main__":
    main()
