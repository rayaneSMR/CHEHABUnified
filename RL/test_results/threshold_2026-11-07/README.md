# Threshold benchmarks: CMO-RL vs. unconstrained agent (2026-11-07)

Evaluation of the joint unified agent on the threshold benchmarks, programs whose initial
estimated noise is 80-100% of a budget, so that the noise constraint binds.

- **Dataset:** `RL/fhe_rl/datasets/threshold_benchmarks.txt`, 60 programs: lines 1-20 for
  B = 230, 21-40 for B = 236, 41-60 for B = 369 (multiplicative depth 6 for 230/236, 9-10 for 369).
- **Agent:** `RL/fhe_rl/trained_models/unified_joint_noise_19038296_best_4.6M.zip`, preference
  w = [1, 0].
  - **CMO-RL (constrained):** the agent runs with the test budget B.
    Files `eval_threshold_benchmarks_b<B>_<job>.*`, merged in `eval_threshold_benchmarks_ALL.xlsx`.
  - **Unconstrained:** the same agent runs with budget 9,000,000 (no constraint during the
    search); the rollback still uses B. Files `eval_threshold_benchmarks_b<B>_agent9000000_<job>.*`,
    merged in `eval_threshold_benchmarks_agent9000000_ALL.xlsx`.
- **Rollback:** best checkpoint within B according to the noise estimator that is also
  certified decryptable by the SEAL noise bound (N = 16384, t = 786433, q = BFVDefault(16384)),
  with the corrected bound of `f4a48116`.
- **Code:** branch `unified-ram-film` at `f4a48116`. Jobs 19142144-19142147 (B = 230, 236) and
  19142249, 19142251 (B = 369).

## Results (programs that start within the budget)

| B | Agent | Over budget before rollback | After rollback | Certified | Cost reduction after rollback (%) |
|---|---|---|---|---|---|
| 230 | CMO-RL | 22 / 40 | 0 | 40 / 40 | 18.26 |
| 230 | Unconstrained | 26 / 40 | 0 | 40 / 40 | 16.81 |
| 236 | CMO-RL | 27 / 40 | 0 | 40 / 40 | 18.57 |
| 236 | Unconstrained | 26 / 40 | 0 | 40 / 40 | 16.81 |
| 369 | CMO-RL | 13 / 60 | 0 | 40 / 60 | 23.75 |
| 369 | Unconstrained | 19 / 60 | 0 | 40 / 60 | 20.81 |

At B = 369, the 20 programs generated for that budget (depth 9-10) cannot be certified by the
bound with these parameters; for them the rollback returns the input.
Earlier runs of this experiment (jobs 19135166-19135171) used the bound before its fix,
which certified no program of depth >= 6; they are not kept.
