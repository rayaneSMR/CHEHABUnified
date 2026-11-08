# End-to-end evaluation of the joint unified agent with the SEAL noise-bound certificate (2026-11-07)

Rerun of the end-to-end evaluation of `RL/test_results/hpc_done/` with the corrected SEAL
noise bound applied in the rollback.

- **Agent:** `RL/fhe_rl/trained_models/unified_joint_noise_19038296_best_4.6M.zip`.
- **Benchmarks:** the 46 instances of the 13 benchmark families (one file per family and budget).
- **Budgets:** B = 230, 236, 369 and 9,000,000 (unconstrained). **Preferences:** the 10 preferences
  w = [1 - w_keys, w_keys], w_keys = 0, 0.1, ..., 0.9.
- **Rollback:** best checkpoint within B according to the noise estimator that is also certified
  decryptable by the SEAL noise bound (N = 16384, t = 786433, q = BFVDefault(16384)), with the
  corrected bound of `f4a48116`. If no checkpoint is certified, the input program is returned.
- **Protocol:** `scripts/run_benchmarks_unified.py`. Each program is compiled by CHEHAB, built and
  executed with SEAL (N = 16384, t = Batching(16384, 20), q = BFVDefault(16384)), and the decrypted
  outputs are compared with the expected values (`outputs_match`).
- **Code:** branch `unified-ram-film` at `bed81510`. Jobs 19142354-19142412.

## Results

- 1,840 runs (46 instances x 10 preferences x 4 budgets), all compiled and executed.
- 1,600 runs with a reference output: all correct. 240 runs on the 6 random polynomial trees have
  no reference output.
- 1,760 / 1,840 runs certified. The 80 others are the two depth-9 trees `tree_100-50_10_1` and
  `tree_100-100_10_1` (all budgets and preferences): the bound cannot certify their input, so the
  rollback returns the input program. SEAL still decrypts them with 62-66 bits of remaining noise budget.
- Constraint satisfaction (within-budget programs, agent / safe violations): identical to
  `hpc_done`: 1.4% / 0% at B = 230, 1.1% / 0% at B = 236, 1.3% / 0% at B = 369, 0% / 0% at 9M.
- Compared with `hpc_done`, only 6 runs return a different program, all on the two depth-9 trees.
  Without these two trees, the trade-off curve at B = 369 is unchanged.

## Files

- `e2e_<benchmark>_b<budget>_<jobid>.csv`: raw results.
- `e2e_ALL.xlsx`: all runs, written by `python scripts/merge_eval_results.py <this folder>`.
