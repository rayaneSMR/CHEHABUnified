# Original CHEHAB RL agent: end-to-end evaluation on the fixed code (2026-11-07)

Re-evaluation of the original single-objective CHEHAB RL agent after the correctness
fixes (see CORRECTNESS_ISSUES.md), to check whether it needs retraining.

- **Agent:** `RL/fhe_rl/trained_models/agent_dynamic_llm_data.zip` (TRAE embeddings, 84 rules
  of `RL/rules.txt`, no rotation rules, no noise constraint, no preference). Same model as in
  the earlier CHEHAB RL and MORL results.
- **Code:** branch `unified-ram-film` at `87533b86` (all correctness fixes). Sort was rerun at
  `2ce7b1f2` (constant-folding fix), because `sort_4` did not compile before it.
- **Protocol:** `scripts/run_benchmarks_unified.py --framework original`, one run per
  benchmark (no budget, no preference). Each program is compiled by CHEHAB, built and
  executed with SEAL (N = 16384, t = Batching(16384, 20), q = BFVDefault(16384)), and the
  decrypted outputs are compared with the expected values (`outputs_match`).
- **Jobs:** 19125663-19125675 (Slurm), sort rerun 19133852.

## Results

46 benchmarks, all compiled and executed:
- 40 with a reference output: all correct (`outputs_match = True`).
- 6 random polynomial trees: no reference output, not checked.

## Files

- `e2e_original_<benchmark>_<jobid>.csv`: raw results, one file per benchmark family.
- `e2e_original_ALL.xlsx`: all benchmarks (sheet `all_runs`) and a summary (sheet `summary`),
  written by `python scripts/merge_eval_results.py <this folder>`.
