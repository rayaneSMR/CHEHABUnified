# Ablation of the constraint mechanisms: end-to-end SEAL evaluation (2026-11-09)

Execution time and rotation key size of the circuits produced by six agents trained with different
constraint mechanisms, with and without safety rollback, compiled and executed with SEAL.

- **Agents** (folder: model, constraint method):
  - `cmorl`: `RL/fhe_rl/trained_models/unified_joint_noise_19038296_best_4.6M.zip`, `nato_sc` (Lag-PID + NATO-SC).
  - `unconstrained`, `v4_mb` (margin barrier), `v4_nmask` (noise masking), `v4_mb_film` (margin
    barrier + FiLM), `v5_focops` (FOCOPS + NATO-SC): the frozen models of branch `HPC_Status`,
    `results/ablation_unified/e2e_10pref/models/<agent>.zip`, methods `none`, `margin_barrier`,
    `noise_masking`, `margin_barrier`, `nato_sc`.
- **Benchmarks:** the 46 instances of the 13 benchmark families. **Budgets:** 230, 236, 369.
  **Preferences:** [1, 0], [0.9, 0.1], [0.6, 0.4].
- **no_rollback/:** the compiler gets the agent's final program (no estimator check, no earlier
  checkpoint). The SEAL noise bound still applies: if it does not certify the final program, the
  input is compiled. All six agents.
- **rollback/:** best checkpoint within the budget according to the noise estimator that is also
  certified by the SEAL bound, as in `e2e_certified_2026-11-07`. The four constrained alternatives
  and the unconstrained agent (`METHOD=none`); the rollback runs of CMO-RL are in `e2e_certified_2026-11-07`.
- **Bound:** corrected SEAL bound of `f4a48116` (N = 16384, t = 786433, q = BFVDefault(16384)).
- **Code:** branch `unified-ram-film` at `a55e5fb8`. Jobs 19294958-19295453 (no_rollback),
  19297325-19297566 (rollback), and a later batch for `rollback/unconstrained`.

## Files

- `<mode>/<agent>/e2e_<benchmark>_b<budget>_<jobid>.csv`: raw results (39 files per agent, 414 runs).
- `<mode>/<agent>/e2e_ALL.xlsx`: all runs of that agent, written by
  `python scripts/merge_eval_results.py <mode>/<agent>/`.
