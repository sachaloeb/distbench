# FACTS.md — Verified numbers for CS4545 Assignment 1 Report

All numbers from 3 runs per configuration, N=10, k=3, f=1 unless noted.
Sweep data in `py/results/sweeps/`.

## Scenario Results (Section 4)

| # | Config | Outcome |
|---|--------|---------|
| 1 | dolev_multi_sender | All 10 nodes delivered all 3 messages; ~259 total messages (base) |
| 2 | dolev_multi_message | All 10 nodes delivered messages 0,1,2; no duplicates; ~259 total messages |
| 3 | dolev_integrity | 0 deliveries by any correct node (weak integrity holds) |
| 3b| dolev_integrity_strong | REAL delivered to all 9 correct nodes; FAKE never delivered (content-keyed state) |
| 4 | dolev_no_totality | Exactly node1 delivers (via MD.1); other 8 correct nodes do not (strict non-empty subset, optimized=true, byzantine_reach=1) |
| 5 | dolev_fault_tolerant | All 9 correct nodes delivered; node8 (passive Byzantine) delivered 0 |

## Sweep: vs N (Section 5.1)

Setup: f=1, k=3, b=0, 3 runs per point, N ∈ {6, 8, 10, 15, 20, 30}.

| N  | Base msgs  | Opt msgs  | Base latency (s) | Opt latency (s) |
|----|-----------|-----------|------------------|-----------------|
| 6  | 45        | 25        | 0.36             | 0.25            |
| 8  | 113       | 36        | 0.36             | 0.28            |
| 10 | 259       | 43        | 0.34             | 0.30            |
| 15 | 2,143     | 78        | 0.53             | 0.48            |
| 20 | 10,079    | 126       | 0.70             | 0.59            |
| 30 | 241,969   | 444       | 0.82             | 0.91            |

**Trend:** Base Dolev message count grows super-linearly (exponentially in practice) with N — every simple path is relayed, and the number of paths in a 3-regular Harary graph explodes. Optimized stays roughly linear. Latency increases mildly with N (longer shortest paths). At N=30 optimized latency slightly exceeds base because MD.2 empty-path relay adds an extra hop before some nodes can deliver.

## Sweep: vs Byzantine count b (Section 5.2)

Setup: N=10, f=2, k=5, 3 runs per point, b ∈ {0, 1, 2}.

| b | Base msgs   | Opt msgs | Base latency (s) | Opt latency (s) |
|---|------------|----------|------------------|-----------------|
| 0 | 10,355     | 113      | 0.33             | 0.22            |
| 1 | 3,133      | 112      | 0.33             | 0.23            |
| 2 | 1,067      | 97       | 0.47             | 0.35            |

**Trend:** More Byzantine (passive) nodes → fewer messages (they don't relay). Latency stays flat for b=0,1 but rises at b=f=2 (fewer honest paths, delivery takes longer to accumulate f+1=3 disjoint paths). Optimized is ~100× fewer messages than base at k=5.

## Sweep: vs Connectivity k (Section 5.3)

Setup: N=10, f=1, b=0, 3 runs per point, k ∈ {3, 4, 5, 6, 7, 8}.

| k | Base msgs   | Opt msgs | Base latency (s) | Opt latency (s) |
|---|------------|----------|------------------|-----------------|
| 3 | 259        | 44       | 0.37             | 0.35            |
| 4 | 1,826      | 71       | 0.31             | 0.28            |
| 5 | 10,355     | 95       | 0.21             | 0.19            |
| 6 | 39,988     | 135      | 0.18             | 0.20            |
| 7 | 133,513    | 147      | 0.11             | 0.12            |
| 8 | 312,845    | 146      | 0.11             | 0.10            |

**Trend:** Higher connectivity dramatically increases base message count (more paths, exponential blowup). Latency drops with k (more and shorter disjoint paths → earlier delivery). Optimized message count grows slowly (MD.1 delivers on first hop, MD.2/5 cut off relaying). At k=8 the base sends 312K messages while optimized sends 146.

## Effect of Optimizations (Section 5.4)

At N=10, k=3, f=1 (mean of 3 runs):
- Base: 259 messages
- Optimized: 43 messages
- **Reduction: −83%**

Across all sweep points (mean):
- Base: ~56,788 messages
- Optimized: ~127 messages
- **Reduction: ~99.8%**

The savings increase with network size and connectivity. MD.1 provides immediate delivery for direct neighbours. MD.2/5 stop all further relaying after delivery. MD.3/4 prune per-neighbour.

## Latency Definition

Latency = `delivery_time - broadcast_time` in seconds. `broadcast_time` is the wall-clock timestamp set by the source at broadcast time. All nodes share one clock (single-machine, offline transport). Source's self-delivery latency is 0s.

## Test Suite

19 tests, all passing:
- 9 unit tests for disjoint-path check (including 200-iteration randomized property test vs brute force)
- 2 validation placeholder tests
- 8 integration tests (5 scenarios × 3 runs each + base vs optimized comparison)

## Docker (P7)

Commands to run:
```
python py/dockerize.py -c configs/dolev.yaml -a dolev -t 20 -vv
sudo docker compose up --build
```
Status: NOT VERIFIED on this machine (Docker not available during this session).
