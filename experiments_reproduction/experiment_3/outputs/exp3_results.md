# Experiment 3: Safety Rollback & Synthetic Near-Threshold Benchmark

**Execution Timestamp:** 2026-11-03T11:12:14.330328+00:00
**Unified Agent Model:** `fheEnvUnified` (RL/fhe_rl/env_unified.py)
**Total Runtime:** 5.39 seconds

## 1. Synthetic Near-Threshold Dataset Composition

| Target Budget | Count | Target Range | Min Noise | Max Noise | Mean Noise | Mean % of Budget | Within Budget Count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 230 | 20 | 80-100% of 230 | 211.08 | 215.87 | 213.54 | 92.8 | 20 |
| 236 | 20 | 80-100% of 236 | 211.08 | 215.87 | 213.54 | 90.5 | 20 |
| 369 | 20 | 80-100% of 369 | 316.02 | 356.59 | 339.34 | 92.0 | 20 |

## 2. Trajectory Rollback Audit Verification

- **Total Episodes Audited:** 360
- **Mismatches Against Safe Final Output:** 0 (100.0% mathematical concordance)
- **Selection Rule:** Lowest-cost intermediate state satisfying `noise <= budget`; fallback to initial expression if infeasible.

## 3. Constrained vs Unconstrained Performance on Threshold Expressions

| Agent | B=230 Safe CR% | B=236 Safe CR% | B=369 Safe CR% | Average Safe CR% |
| --- | --- | --- | --- | --- |
| Unconstrained + Safety | 31.53 | 31.53 | 39.02 | 34.03 |
| Constrained (Lag-PID) + Safety | 36.26 | 39.22 | 38.4 | 37.96 |
| Advantage (Constrained - Unconstrained) | +4.73 pp | +7.69 pp | -0.62 pp | +3.93 pp |

## 4. Violation Rates Before and After Rollback (Within-Budget Expressions)

| Agent | B=230 before | B=230 after | B=369 before | B=369 after |
| --- | --- | --- | --- | --- |
| Unconstrained | 47.5% (19/40) | 0.0% (0/40) | 23.3% (14/60) | 0.0% (0/60) |
| Constrained (Lag-PID) | 52.5% (21/40) | 0.0% (0/40) | 18.3% (11/60) | 0.0% (0/60) |

## 5. Agent Ablation with Rollback on Original Benchmark

| Agent | B=230 Safe CR% | B=236 Safe CR% | B=369 Safe CR% | B=9M Safe CR% | Average Safe CR% | Safe Violations |
| --- | --- | --- | --- | --- | --- | --- |
| Unconstrained | 87.23 | 87.23 | 71.59 | 66.08 | 78.03 | 0 (0.0%) |
| V4 Margin Barrier | 84.41 | 85.89 | 65.86 | 58.78 | 73.74 | 0 (0.0%) |
| V4 Noise Masking | 86.68 | 86.87 | 65.7 | 56.64 | 73.97 | 0 (0.0%) |
| V4 MB + FiLM | 83.32 | 83.94 | 63.91 | 56.9 | 72.02 | 0 (0.0%) |
| V5 FOCOPS + NATO-SC | 84.52 | 85.18 | 69.81 | 63.37 | 75.72 | 0 (0.0%) |
| V5 Lag-PID + NATO-SC | 86.52 | 86.55 | 71.5 | 65.29 | 77.46 | 0 (0.0%) |
