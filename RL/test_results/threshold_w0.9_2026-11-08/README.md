# Threshold benchmarks at w = [0.9, 0.1]: CMO-RL vs. unconstrained agent (2026-11-08)

Same experiment as `RL/test_results/threshold_2026-11-07/` (same dataset, agent, rollback with
the corrected SEAL noise bound, and code), with preference w = [0.9, 0.1] instead of [1, 0].

- **Dataset:** `RL/fhe_rl/datasets/threshold_benchmarks.txt` (lines 1-20 for B = 230, 21-40 for
  B = 236, 41-60 for B = 369).
- **Agent:** `RL/fhe_rl/trained_models/unified_joint_noise_19038296_best_4.6M.zip`.
  - **CMO-RL:** agent runs with the test budget B. Files `eval_threshold_benchmarks_b<B>_<job>.*`,
    merged in `eval_threshold_benchmarks_ALL.xlsx`.
  - **Unconstrained:** agent runs with budget 9,000,000; the rollback still uses B. Files
    `eval_threshold_benchmarks_b<B>_agent9000000_<job>.*`, merged in
    `eval_threshold_benchmarks_agent9000000_ALL.xlsx`.
- **Jobs:** 19203897, 19203900 (B = 230), 19203908, 19203910 (B = 236), 19203915, 19203916 (B = 369).
