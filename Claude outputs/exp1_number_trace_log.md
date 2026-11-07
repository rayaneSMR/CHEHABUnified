# Experiment 1 — number trace log

Every number in `exp1_cmorl_vs_chehabrl.tex` falls into one of three groups.

## A. Placeholder numbers (red `\ex{}` in the LaTeX) — NOT results
Every per-benchmark value (noise bits, time in ms, key counts, MB) in Fig. `fig:exp1`,
Table `tab:exp1-details` and Table `tab:exp1-summary` is illustrative and was invented
for layout. Replace all of them with measured values.

Derived placeholders are computed from the per-benchmark placeholders (script: `data.py`), so they stay internally consistent:
| Quantity in text | Placeholder | How derived |
|---|---|---|
| Violations (baseline / CMO-RL) | 10/14, 0/14 | count of noise > B (230) |
| Max. overshoot | 17.8% (HD32, 271 bits) | (271−230)/230 |
| Geomean speedup | 1.02× (range 0.998–1.063×) | geomean of T_base/T_cmo |
| Lower-or-equal time | 13/14 (CMO-RL), 2/14 (baseline) | per-benchmark comparison |
| Slowest case | L2-16, +1 ms (0.2%) | 431 vs 430 |
| Total keys | 64 vs 44 | sum |
| Total key size | 1152 MB vs 792 MB, −31% | keys × 18 MB; 1 − 44/64 |
| Geomean key-size ratio | 0.69 | geomean of K_cmo/K_base |
| Fig. (a) bar heights | noise / 230 | per benchmark |
| Fig. (b) bar heights | T_base / T_cmo | per benchmark |
| Fig. (c) bar heights | keys × 18 | per benchmark |

When real data arrives, rerun the same derivations and update **all** prose numbers
(Constraint satisfaction, Execution time, Rotation key memory, Summary paragraphs).
Several prose claims depend on the placeholder pattern and must be rechecked:
"largest speedup on the benchmark where RKS decomposes the most rotations",
"Polynomial Regression needs the same 2 keys", "the four complying benchmarks are shallow".

## B. Numbers taken from sources
| Number | Source |
|---|---|
| Budget 230 bits (tightest training budget) | `RL/fhe_rl/env_unified.py`, `DEFAULT_NOISE_BUDGETS = [230, 236, 369, 9_000_000]`; also `run_unified.py` line 39. Value used here is a placeholder choice; confirm. |
| ≈18 MB per serialized Galois key | MORL thesis (Mokrane, 2025), §5.5.1 "Compiler Metrics", PDF p. ~74 (printed p. 74). Confirm for the PLDI parameters. |
| Preference (0.9, 0.1) | Requested by the author. |
| RKS = NAF decomposition under keys_threshold; 12 = 8 + 4 example | MORL thesis §3.8.5, printed p. 45. |
| CHEHAB RL cost = ops + depth + mult. depth, PPO | MORL thesis §3.8.4, printed pp. 43–44 (describes Sefsaf et al. 2026). |

## C. Open items (blue `\todo{}` in the LaTeX)
1. RKS key threshold used for the baseline.
2. Rollback enabled/disabled for CMO-RL in Exp. 1.
3. Exact budget semantics (estimated consumed noise vs. SEAL remaining budget) and encryption parameters (N, log q).
4. Backend, hardware, number of runs, aggregation (median?), std. dev.
5. Final benchmark list.
6. Decryption-failure evidence for violating circuits.
7. Rotation counts supporting the speedup explanation.
8. Noise breakdown supporting the "why the baseline violates" paragraph (currently a hypothesis).
9. Labels `sec:method`, `sec:rollback`, `sec:exp2` and citation key `chehabrl` must match your paper.
10. I could not inspect the CHEHAB RL paper's figures; the per-benchmark grouped-bar style is my assumption about "graphs similar to CHEHAB RL". Check against that paper.
