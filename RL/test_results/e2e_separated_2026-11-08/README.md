# End-to-end evaluation of the separated pipeline (2026-11-08)

Separated pipeline (Stage 1 ops agent, then Stage 2 rotations agent) on the CHEHAB benchmarks,
compiled and executed with SEAL, for the comparison with the joint unified agent.

- **Stage 1 (ops):** `RL/eval/best_model_model_19038298_nato_sc_film_a_gnn_ops/best_model.zip`
  (HPC training clone), run at w = [1, 0].
- **Stage 2 (rotations):** `RL/eval/best_model_model_19137715_nato_sc_film_a_gnn_rotations/best_model.zip`
  (HPC training clone, 5M steps), run at w on the Stage 1 output.
- **Benchmarks:** the 46 instances of the 13 benchmark families (one file per family).
- **Budget:** B = 230. **Preferences:** [1, 0], [0.9, 0.1], [0.8, 0.2], [0.7, 0.3], [0.6, 0.4].
- **Rollback:** at each stage, best checkpoint within B according to the noise estimator that is
  also certified by the SEAL noise bound (corrected bound of `f4a48116`), as for the joint agent.
- **Protocol:** `scripts/run_benchmarks_unified.py --model-stage2` (same runner as the joint runs).
- **Code:** branch `unified-ram-film` at `67ecb524`. Jobs 19197208-19197220.
- **Joint counterpart:** the B = 230 runs of `RL/test_results/e2e_certified_2026-11-07/`.

## Files

- `e2e_sep_<benchmark>_b230_<jobid>.csv`: raw results (230 runs, all compiled and executed).
- `e2e_separated_ALL.xlsx`: all runs, written by `python scripts/merge_eval_results.py <this folder>`.
