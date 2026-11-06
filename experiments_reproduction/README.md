# Reproducing Experiments 2 and 3

The reporting scripts load CSV files produced by the model-evaluation stage.
They do not use `hpc_results`.

From the repository root, run all six unified 4-preference checkpoints and
then generate both reports with:

```powershell
python experiments_reproduction/run_all.py
```

To also compile and execute the optimized programs and report measured
execution time and rotation-key size, use:

```powershell
python experiments_reproduction/run_all.py --measured
```

This runs the SEAL sweep twice: once with rollback disabled for Experiment 2
and once with rollback enabled for Experiment 3. The measured CSVs are stored
under `results/ablation_unified/seal_4pref/{no_rollback,rollback}/raw/` and
are included in each report as `seal_measured.csv`. The sweep requires the
repository's compiled benchmark programs and SEAL build dependencies.

The command evaluates each checkpoint with `python -m fhe_rl ... test
--test_mode v2`, writing `original.csv` and `threshold.csv` below:

```text
results/ablation_unified/<agent>_4pref/eval_<run-id>/
```

Run only one experiment's evaluation stage when needed:

```powershell
python experiments_reproduction/experiment_2/run_models.py
python experiments_reproduction/experiment_3/run_models.py
```

The six checkpoints are expected at
`RL/fhe_rl/trained_models/unified_noise_abl_<agent>_4pref[_best].zip`.
Use `--model agent=path` to supply a checkpoint stored elsewhere. The model
evaluation environment must include the dependencies used by `fhe_rl`,
including PyTorch Geometric for the GNN embedder.

To inspect commands without executing them:

```powershell
python experiments_reproduction/run_model_evaluations.py --dry-run
```

After CSV generation, the existing reporting scripts can be run independently:

```powershell
python experiments_reproduction/experiment_2/run_experiment_2.py --source unified
python experiments_reproduction/experiment_3/run_experiment_3.py --source unified
```
