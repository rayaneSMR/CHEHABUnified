#!/usr/bin/env python3
"""Experiment 1 - NNLS noise-estimator validation (subparts 1A, 1B, 1C).

Run (from anywhere):
    python experiments_reproduction/experiment_1/run_experiment_1.py

What it does
    1A  feature vs measured-noise relationship (Pearson table + plots)
    1B  NNLS fit with non-negativity and zero bias -> coefficient table
    1C  estimated-vs-measured accuracy (MAE, MSE, RMSE, R2) + plots
Plus clearly-labelled SUPPLEMENTARY checks that are NOT part of the original code:
    seeded k-fold CV, refit without budget-exhausted rows, error-direction and
    per-depth error tables.

All numbers are written exactly as computed (no comparison with, or remarks about,
manuscript values in the CSV tables).

Fidelity to the repo
    The model is fitted with the same call as RL/pytrs/noise_estimator.py
    (NoiseEstimator.__init__):
        LinearRegression(fit_intercept=False, positive=True)
    on the same columns, in the same order, on the whole CSV, with target
        369 - Remaining_noise_budget.
    There is no train/test split and no random seed in the original code, so the
    primary metrics are IN-SAMPLE. Nothing is copied from the repo: the script imports
    the repo's own NoiseEstimator (RL/pytrs/noise_estimator.py) and checks that its
    coefficients equal the refit done here, so later changes in the repo are detected.

Input : RL/fhe_rl/datasets/noise_estimator_stats_dataset.csv (read-only, not copied)
Output: experiment_1/outputs/  (CSV/MD tables, PNG plots, run_metadata.json)

Exit codes: 0 ok | 1 unexpected error | 2 data/validation error (includes a refit that
disagrees with the repo's NoiseEstimator).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import scipy  # noqa: E402
import sklearn  # noqa: E402
from scipy.optimize import nnls  # noqa: E402
from sklearn.linear_model import LinearRegression  # noqa: E402
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score  # noqa: E402
from sklearn.model_selection import KFold  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]  # experiments_reproduction/experiment_1 -> repo root
DEFAULT_CSV = REPO_ROOT / "RL" / "fhe_rl" / "datasets" / "noise_estimator_stats_dataset.csv"
DEFAULT_OUT = HERE / "outputs"

# --------------------------------------------------------------------------- #
# Constants taken from the repo
# --------------------------------------------------------------------------- #
NOISE_BUDGET = 369  # NoiseEstimator.__init__ default: target = 369 - Remaining_noise_budget
REMAINING = "Remaining_noise_budget"

# Feature columns in the exact order used by NoiseEstimator.__init__
MODEL_COLUMNS = [
    "add",
    "sub",
    "multiply_plain",
    "rotate_rows",
    "negate",
    "multiply",
    "Depth",
    "Multiplicative Depth",
]

# Manuscript feature name for each code column
NAMES = {
    "Multiplicative Depth": "Multiplicative depth",
    "Depth": "Expression depth",
    "negate": "Negations",
    "add": "Additions",
    "sub": "Subtractions",
    "multiply_plain": "Plaintext multiplications",
    "multiply": "Ciphertext multiplications",
    "rotate_rows": "Rotations",
}
# Order used in the reproduction spec's tables
REPORT_ORDER = [
    "Multiplicative Depth",
    "Depth",
    "negate",
    "add",
    "sub",
    "multiply_plain",
    "multiply",
    "rotate_rows",
]

# Repo files whose hash is recorded in run_metadata.json (read in place, never copied)
REPO_SOURCES = ["RL/pytrs/noise_estimator.py", "RL/pytrs/cost.py"]


class DataError(Exception):
    """Input data or fit failed a validation check (exit code 2)."""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def df_to_md(df: pd.DataFrame, floatfmt: str = "{:.4f}") -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for tup in df.itertuples(index=False, name=None):
        cells = []
        for v in tup:
            if isinstance(v, (float, np.floating)):
                cells.append("" if np.isnan(v) else floatfmt.format(v))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# --------------------------------------------------------------------------- #
# Repo provenance (files are read in place, never copied)
# --------------------------------------------------------------------------- #
def repo_source_hashes() -> dict:
    out = {}
    for rel in REPO_SOURCES:
        p = REPO_ROOT / rel
        out[rel] = hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() if p.is_file() else "not found"
    return out


def load_repo_estimator(csv_path: Path):
    """Build the repo's own NoiseEstimator on the same CSV.

    Returns ((estimator, default_noise_budget), note) or (None, reason) if the repo module
    cannot be imported (e.g. missing dependency); the script then continues without the cross-check.
    """
    pytrs = REPO_ROOT / "RL" / "pytrs"
    if not (pytrs / "noise_estimator.py").is_file():
        return None, "RL/pytrs/noise_estimator.py not found"
    for p in (str(REPO_ROOT / "RL"), str(pytrs)):  # the repo imports expr/parser/cost as top-level modules
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        mod = importlib.import_module("noise_estimator")
        est = mod.NoiseEstimator(stats_dataset_path=csv_path)
        default_budget = inspect.signature(mod.NoiseEstimator.__init__).parameters["noise_budget"].default
        return (est, default_budget), "ok"
    except Exception as exc:  # noqa: BLE001 - any import/build failure just disables the cross-check
        return None, f"could not import/build repo NoiseEstimator ({type(exc).__name__}: {exc})"


# --------------------------------------------------------------------------- #
# Data + model
# --------------------------------------------------------------------------- #
def load_dataset(csv_path: Path) -> pd.DataFrame:
    if not csv_path.is_file():
        raise DataError(f"dataset not found: {csv_path} (use --csv to point to noise_estimator_stats_dataset.csv)")
    df = pd.read_csv(csv_path)
    required = MODEL_COLUMNS + [REMAINING]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataError(f"missing required columns: {missing}")
    if len(df) == 0:
        raise DataError("dataset is empty")
    for c in required:
        if not pd.api.types.is_numeric_dtype(df[c]):
            raise DataError(f"column {c!r} is not numeric")
    if df[required].isna().any().any():
        raise DataError("dataset has missing values in required columns")
    df = df.copy()
    df["used_noise"] = NOISE_BUDGET - df[REMAINING]
    if (df["used_noise"] < 0).any():
        raise DataError(f"{REMAINING} exceeds the assumed total budget {NOISE_BUDGET} in some rows")
    return df


def fit_model(frame: pd.DataFrame) -> LinearRegression:
    """Identical to NoiseEstimator.__init__ (RL/pytrs/noise_estimator.py)."""
    model = LinearRegression(fit_intercept=False, positive=True)
    model.fit(frame[MODEL_COLUMNS], frame["used_noise"])
    return model


def fit_and_check(df: pd.DataFrame):
    model = fit_model(df)
    coef = np.asarray(model.coef_, dtype=float)
    if float(model.intercept_) != 0.0:
        raise DataError("fitted intercept is not zero")
    if (coef < 0).any():
        raise DataError("negative coefficient found despite positive=True")
    ref, _ = nnls(df[MODEL_COLUMNS].to_numpy(dtype=float), df["used_noise"].to_numpy(dtype=float))
    if not np.allclose(ref, coef, atol=1e-6):
        raise DataError("sklearn positive LinearRegression disagrees with scipy.optimize.nnls")
    return model, coef


# --------------------------------------------------------------------------- #
# 1A - feature vs noise
# --------------------------------------------------------------------------- #
def correlation_table(df: pd.DataFrame) -> pd.DataFrame:
    """Pearson r between each feature and the consumed noise (NaN if the feature is constant)."""
    y = df["used_noise"]
    rows = []
    for col in REPORT_ORDER:
        x = df[col]
        r = float("nan") if float(x.std()) == 0.0 else float(x.corr(y))
        rows.append({"Feature": NAMES[col], "Pearson r": r})
    return pd.DataFrame(rows)


def mean_noise_by_md(df: pd.DataFrame, censored: pd.Series) -> pd.DataFrame:
    g = df.groupby("Multiplicative Depth")["used_noise"]
    t = g.agg(rows="size", mean_noise="mean", min_noise="min", max_noise="max").reset_index()
    t = t.rename(columns={"Multiplicative Depth": "multiplicative_depth"})
    exh = df[censored].groupby("Multiplicative Depth").size()
    t["rows_budget_exhausted"] = exh.reindex(t["multiplicative_depth"]).fillna(0).astype(int).to_numpy()
    return t


# --------------------------------------------------------------------------- #
# 1C - accuracy
# --------------------------------------------------------------------------- #
def accuracy(y: np.ndarray, p: np.ndarray) -> dict:
    mse = float(mean_squared_error(y, p))
    return {
        "MAE": float(mean_absolute_error(y, p)),
        "MSE": mse,
        "RMSE": math.sqrt(mse),
        "R2": float(r2_score(y, p)),
        "R2_uncentered": float(1.0 - np.sum((y - p) ** 2) / np.sum(y**2)),
    }


def error_direction(y: np.ndarray, p: np.ndarray, label: str) -> dict:
    res = p - y  # estimate - measured; negative = underestimate
    n = len(res)
    return {
        "subset": label,
        "rows": n,
        "underestimated (n)": int((res < 0).sum()),
        "underestimated (%)": 100.0 * float((res < 0).mean()),
        "overestimated (n)": int((res > 0).sum()),
        "overestimated (%)": 100.0 * float((res > 0).mean()),
        "mean signed error (est - measured)": float(res.mean()),
        "max underestimation (bits)": float(max(0.0, -res.min())),
        "max overestimation (bits)": float(max(0.0, res.max())),
        "rows underestimated by > 5 bits": int((res < -5).sum()),
    }


def error_by_md(df: pd.DataFrame, pred: np.ndarray, censored: pd.Series) -> pd.DataFrame:
    tmp = pd.DataFrame(
        {"md": df["Multiplicative Depth"].to_numpy(), "actual": df["used_noise"].to_numpy(), "est": pred}
    )
    tmp["err"] = tmp["est"] - tmp["actual"]
    tmp["abs_err"] = tmp["err"].abs()
    t = tmp.groupby("md").agg(
        rows=("err", "size"),
        mean_measured=("actual", "mean"),
        mean_estimated=("est", "mean"),
        mae=("abs_err", "mean"),
        mean_signed_error=("err", "mean"),
        min_signed_error=("err", "min"),
        max_signed_error=("err", "max"),
    )
    t = t.reset_index().rename(columns={"md": "multiplicative_depth"})
    exh = df[censored].groupby("Multiplicative Depth").size()
    t["rows_budget_exhausted"] = exh.reindex(t["multiplicative_depth"]).fillna(0).astype(int).to_numpy()
    return t


def cross_validate(df: pd.DataFrame, folds: int, seed: int) -> np.ndarray:
    oof = np.zeros(len(df))
    kf = KFold(n_splits=folds, shuffle=True, random_state=seed)
    for tr, te in kf.split(df):
        m = fit_model(df.iloc[tr])
        oof[te] = m.predict(df.iloc[te][MODEL_COLUMNS])
    return oof


# --------------------------------------------------------------------------- #
# Plots (minimalist, paper style: no titles, no grid, no legends, no captions)
# --------------------------------------------------------------------------- #
POINT_COLOR = "tab:blue"
FIT_COLOR = "red"
YLABEL = "Consumed noise (bits)"


def apply_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 9,
            "axes.linewidth": 0.6,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "pdf.fonttype": 42,
            "savefig.dpi": 300,
        }
    )


def save_fig(fig, path: Path) -> list[str]:
    """Save the figure as a PNG; returns the file names written."""
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return [path.name]


def _scatter(ax, x, y, label=None) -> None:
    pts = pd.DataFrame({"x": np.asarray(x), "y": np.asarray(y)}).drop_duplicates()
    ax.scatter(pts["x"], pts["y"], s=6, color=POINT_COLOR, alpha=0.6, linewidths=0, label=label)


def plot_feature_grid(df: pd.DataFrame, coef_by_col: dict, path: Path) -> list[str]:
    """One panel per feature: x = feature, y = consumed noise, points + the NNLS linear term (red).

    The red line is the learned NNLS term for that feature alone (coefficient * x, no intercept).
    It is drawn even where it does not follow the points (e.g. coefficient 0 -> flat line).
    """
    fig, axes = plt.subplots(2, 4, figsize=(10, 4.6), sharey=True)
    for ax, col in zip(axes.ravel(), REPORT_ORDER):
        _scatter(ax, df[col], df["used_noise"])
        xmax = max(float(df[col].max()), 1.0)
        xs = np.array([0.0, xmax])
        ax.plot(xs, float(coef_by_col[col]) * xs, color=FIT_COLOR, lw=1.2)
        ax.set_xlim(-0.03 * xmax, 1.03 * xmax)
        ax.set_ylim(bottom=0)
        ax.set_xlabel(NAMES[col])
    for ax in axes[:, 0]:
        ax.set_ylabel(YLABEL)
    return save_fig(fig, path)


def plot_md(df: pd.DataFrame, md_coef: float, path: Path) -> list[str]:
    x = df["Multiplicative Depth"]
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    _scatter(ax, x, df["used_noise"])
    xmax = float(x.max())
    ax.plot([0.0, xmax], [0.0, md_coef * xmax], color=FIT_COLOR, lw=1.2)
    ax.set_xticks(range(0, int(xmax) + 1))
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Multiplicative depth")
    ax.set_ylabel(YLABEL)
    return save_fig(fig, path)


def plot_est_vs_actual(y: np.ndarray, p: np.ndarray, path: Path) -> list[str]:
    fig, ax = plt.subplots(figsize=(3.6, 3.6))
    _scatter(ax, y, p, label="Predicted")
    hi = float(max(y.max(), p.max())) * 1.03
    ax.plot([0, hi], [0, hi], color="black", ls="--", lw=0.8, label="Ideal")
    ax.set_xlim(0, hi)
    ax.set_ylim(0, hi)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("True noise (bits)")
    ax.set_ylabel("Predicted noise (bits)")
    ax.legend(loc="upper left", frameon=False, fontsize=8, handletextpad=0.4, markerscale=2)
    return save_fig(fig, path)


def plot_residuals(y: np.ndarray, p: np.ndarray, path: Path) -> list[str]:
    res = p - y
    lo, hi = math.floor(res.min()) - 0.5, math.ceil(res.max()) + 1.5
    fig, ax = plt.subplots(figsize=(4.2, 3.0))
    bins = np.arange(lo, hi, 1.0)
    ax.hist(res[res < 0], bins=bins, color="tab:red", alpha=0.75, label="Underestimate")
    ax.hist(res[res >= 0], bins=bins, color="tab:blue", alpha=0.75, label="Overestimate")
    ax.axvline(0, color="black", lw=0.6)
    ax.legend(frameon=False, fontsize=8)
    ax.set_yscale("log")
    ax.set_xlabel("Estimate - measured (bits)")
    ax.set_ylabel("Rows")
    return save_fig(fig, path)


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def build_report(c: dict) -> str:
    L = []
    L.append("# Experiment 1 - NNLS noise-estimator validation: results\n")
    L.append(
        f"Generated by `run_experiment_1.py`. Dataset: `{c['csv_rel']}` ({c['n_rows']} rows, SHA-256 `{c['csv_sha'][:16]}...`). "
        f"Target = {NOISE_BUDGET} - `{REMAINING}`. Model: `LinearRegression(fit_intercept=False, positive=True)` fitted on all rows "
        "(same call as `RL/pytrs/noise_estimator.py`). **All primary metrics are in-sample**: the original code has no train/test split and no seed.\n"
    )
    L.append(
        "Terminology: the manuscript's *expression depth* is the code column `Depth` (`get_normal_depth`). `cost.py` calls the same "
        "quantity `D_circ` (circuit depth) in its cost formula. They are the same feature; the manuscript name is kept.\n"
    )
    L.append("## 1A. Feature - noise relationship (Pearson r)\n")
    L.append(df_to_md(c["corr"]) + "\n")
    L.append("Plots: `1A_feature_vs_noise` (all eight features), `1A_multiplicative_depth_vs_noise` (PNG). The red line is the learned NNLS term (coefficient x feature, no intercept).\n")
    L.append("Mean measured noise by multiplicative depth:\n")
    L.append(df_to_md(c["mean_md"]) + "\n")
    L.append("## 1B. Learned NNLS coefficients\n")
    L.append(df_to_md(c["coef"], floatfmt="{:.6f}") + "\n")
    L.append(
        f"Non-zero coefficients: {', '.join(c['nonzero_names'])}. "
        "Intercept is exactly 0 (fit_intercept=False). The sklearn solution equals `scipy.optimize.nnls` to within 1e-6.\n"
    )
    L.append("## 1C. Estimation accuracy (in-sample)\n")
    L.append(df_to_md(c["metrics"], floatfmt="{:.6f}") + "\n")
    L.append("Plots: `1C_estimated_vs_actual`, `1C_residuals` (PNG).\n")
    L.append("### Error direction (estimate - measured; negative = underestimate)\n")
    L.append(df_to_md(c["direction"]) + "\n")
    L.append("### Error by multiplicative depth\n")
    L.append(df_to_md(c["error_md"]) + "\n")
    L.append("### Supplementary checks (not in the original code)\n")
    L.append(df_to_md(c["supp"], floatfmt="{:.4f}") + "\n")
    L.append(
        f"The cross-validation row uses KFold(n_splits={c['cv_folds']}, shuffle=True, random_state={c['cv_seed']}); the folds and seed are "
        "choices made for this reproduction, not values from the repo. `R2` is the standard (centered) R2; `R2_uncentered` is shown "
        "because the model has no intercept.\n"
    )
    L.append("## Interpretation (empirical fit, not a guarantee)\n")
    L.append(
        f"- **Dominant feature.** Multiplicative depth has Pearson r = {c['r_md']:.4f} with measured noise, and its NNLS coefficient is "
        f"{c['md_coef']:.2f} bits per level. NNLS gives non-zero weight only to {', '.join(c['nonzero_names'])}. Additions, subtractions and "
        "ciphertext multiplications are correlated with the depth features, so their raw correlations with noise should not be read as "
        "independent effects.\n"
        f"- **Fit quality.** In-sample MAE {c['acc']['MAE']:.2f} bits, RMSE {c['acc']['RMSE']:.2f}, R2 {c['acc']['R2']:.4f}. The supplementary "
        f"{c['cv_folds']}-fold CV gives MAE {c['cv_acc']['MAE']:.2f}, RMSE {c['cv_acc']['RMSE']:.2f}, R2 {c['cv_acc']['R2']:.4f}, "
        "close to the in-sample values, so with three non-zero parameters on this many rows there is no sign of overfitting. "
        f"Rank agreement between estimate and measurement is Spearman rho = {c['spearman_pred']:.3f} (the measured values take only "
        f"{c['n_unique_measured']} distinct integer values, so there are many ties).\n"
        f"- **Direction of error.** {c['under_pct']:.1f}% of rows are underestimated, by at most {c['max_under']:.1f} bits "
        f"({c['n_under5']} rows by more than 5 bits). Underestimation is the direction the spec flags as risky for decryption failures; "
        "the figure above is an empirical in-sample worst case, not a bound. The largest overestimates come from the "
        f"{c['n_exh']} budget-exhausted row(s), whose measured consumption is only a lower bound, so they are not true overestimates.\n"
        f"- **Coverage limits.** {c['pct_md_le3']:.1f}% of rows have multiplicative depth <= 3 and only {c['n_md_ge7']} rows have depth >= 7, "
        "the range where tight budgets matter. `rotate_rows` is never non-zero, and `multiply_plain` / `negate` are non-zero in only "
        f"{c['n_mp']} / {c['n_neg']} rows, so their zero (or, for negate, small) coefficients reflect scarce data rather than evidence of no effect.\n"
        "- **Usefulness for search guidance.** The fit is tight where the data lives and is cheap to evaluate, which supports using it as an "
        "empirical structural proxy to screen and rank expressions. It does not establish that estimated noise bounds or predicts real "
        "execution noise, and the evidence is thin at high multiplicative depth.\n"
    )
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Experiment 1: NNLS noise-estimator validation (1A, 1B, 1C)")
    ap.add_argument("--csv", default=str(DEFAULT_CSV), help="path to noise_estimator_stats_dataset.csv")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output directory")
    ap.add_argument("--cv-folds", type=int, default=5, help="folds for the supplementary CV (default 5)")
    ap.add_argument("--cv-seed", type=int, default=0, help="seed for the supplementary CV shuffle (default 0)")
    return ap.parse_args(argv)


def run(args) -> int:
    apply_style()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    csv_path = Path(args.csv).resolve()
    df = load_dataset(csv_path)
    censored = df[REMAINING] == 0
    y = df["used_noise"].to_numpy(dtype=float)
    print(f"[data] {len(df)} rows from {csv_path}; budget-exhausted rows (Remaining_noise_budget == 0): {int(censored.sum())}")

    # ---------------- 1B (fit first: 1A/1C use it) ----------------
    model, coef = fit_and_check(df)

    # Cross-check against the repo's own NoiseEstimator (current state of the unified repo)
    repo_info, repo_note = load_repo_estimator(csv_path)
    if repo_info is None:
        print(f"[repo estimator] NOT cross-checked: {repo_note}", file=sys.stderr)
        repo_check = {"checked": False, "note": repo_note}
    else:
        repo_est, repo_default_budget = repo_info
        if repo_default_budget != NOISE_BUDGET:
            raise DataError(
                f"repo NoiseEstimator default noise_budget is {repo_default_budget}, script assumes {NOISE_BUDGET}; update NOISE_BUDGET"
            )
        repo_coef = np.asarray(repo_est.model.coef_, dtype=float)
        diff = float(np.max(np.abs(repo_coef - coef)))
        if diff > 1e-9:
            raise DataError(
                f"refit disagrees with the repo NoiseEstimator (max |coef diff| = {diff:.3g}); "
                "the repo's features/target/model changed, adapt MODEL_COLUMNS / NOISE_BUDGET / fit_model"
            )
        repo_check = {"checked": True, "default_noise_budget": int(repo_default_budget), "max_abs_coef_diff": diff}
        print(f"[repo estimator] refit matches RL/pytrs/noise_estimator.py (max |coef diff| = {diff:.2g})")

    coef_by_col = dict(zip(MODEL_COLUMNS, coef))
    coef_df = pd.DataFrame(
        [{"Feature": NAMES[col], "Learned coefficient": float(coef_by_col[col])} for col in REPORT_ORDER]
    )
    nonzero_cols = [c for c in REPORT_ORDER if coef_by_col[c] > 0]
    coef_df.to_csv(out / "1B_nnls_coefficients.csv", index=False, float_format="%.6f")
    written.append("1B_nnls_coefficients.csv")

    # ---------------- 1A ----------------
    corr = correlation_table(df)
    corr.to_csv(out / "1A_feature_noise_correlation.csv", index=False, float_format="%.6f")
    written.append("1A_feature_noise_correlation.csv")
    mean_md = mean_noise_by_md(df, censored)
    mean_md.to_csv(out / "1A_mean_noise_by_multiplicative_depth.csv", index=False, float_format="%.6f")
    written.append("1A_mean_noise_by_multiplicative_depth.csv")
    fcorr = df[REPORT_ORDER].corr()
    fcorr.index.name = "feature"
    fcorr.round(6).to_csv(out / "1A_feature_correlation_matrix.csv")
    written.append("1A_feature_correlation_matrix.csv")
    written += plot_feature_grid(df, coef_by_col, out / "1A_feature_vs_noise.png")
    written += plot_md(df, float(coef_by_col["Multiplicative Depth"]), out / "1A_multiplicative_depth_vs_noise.png")

    # ---------------- 1C ----------------
    pred = model.predict(df[MODEL_COLUMNS])
    acc = accuracy(y, pred)
    metrics_df = pd.DataFrame([{"Metric": k, "Result": acc[k]} for k in ("MAE", "MSE", "RMSE", "R2")])
    metrics_df.to_csv(out / "1C_accuracy_metrics.csv", index=False, float_format="%.6f")
    written.append("1C_accuracy_metrics.csv")
    spearman_pred = float(pd.Series(pred).corr(pd.Series(y), method="spearman"))

    keep = ~censored.to_numpy()
    dir_df = pd.DataFrame(
        [error_direction(y, pred, "all rows"), error_direction(y[keep], pred[keep], "excluding budget-exhausted rows")]
    )
    dir_df.to_csv(out / "1C_error_direction.csv", index=False, float_format="%.6f")
    written.append("1C_error_direction.csv")
    err_md = error_by_md(df, pred, censored)
    err_md.to_csv(out / "1C_error_by_multiplicative_depth.csv", index=False, float_format="%.6f")
    written.append("1C_error_by_multiplicative_depth.csv")

    # supplementary: refit without exhausted rows, and seeded CV
    supp_rows = []

    def supp_row(label, n, coefs, a):
        row = {"Variant": label, "Rows": n}
        for col in ("Multiplicative Depth", "Depth", "negate"):
            row[f"coef {col}"] = float(coefs[col]) if coefs is not None else float("nan")
        row.update({"MAE": a["MAE"], "MSE": a["MSE"], "RMSE": a["RMSE"], "R2": a["R2"], "R2_uncentered": a["R2_uncentered"]})
        return row

    supp_rows.append(supp_row("in-sample, all rows (primary)", len(df), coef_by_col, acc))
    if censored.any():
        df_k = df[~censored]
        m_k = fit_model(df_k)
        coef_k = dict(zip(MODEL_COLUMNS, np.asarray(m_k.coef_, dtype=float)))
        a_k = accuracy(df_k["used_noise"].to_numpy(dtype=float), m_k.predict(df_k[MODEL_COLUMNS]))
        supp_rows.append(supp_row("in-sample, refit without budget-exhausted rows", len(df_k), coef_k, a_k))
    oof = cross_validate(df, args.cv_folds, args.cv_seed)
    cv_acc = accuracy(y, oof)
    supp_rows.append(supp_row(f"{args.cv_folds}-fold CV out-of-fold, all rows (seed {args.cv_seed})", len(df), None, cv_acc))
    supp_df = pd.DataFrame(supp_rows)
    supp_df.to_csv(out / "1C_supplementary_checks.csv", index=False, float_format="%.6f")
    written.append("1C_supplementary_checks.csv")

    written += plot_est_vs_actual(y, pred, out / "1C_estimated_vs_actual.png")
    written += plot_residuals(y, pred, out / "1C_residuals.png")

    # ---------------- report + metadata ----------------
    md_series = df["Multiplicative Depth"]
    d_all = dir_df.iloc[0]
    try:
        csv_rel = csv_path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        csv_rel = str(csv_path)
    ctx = {
        "csv_rel": csv_rel,
        "csv_sha": sha256_file(csv_path),
        "n_rows": len(df),
        "corr": corr,
        "mean_md": mean_md,
        "coef": coef_df,
        "metrics": metrics_df,
        "direction": dir_df,
        "error_md": err_md,
        "supp": supp_df,
        "cv_folds": args.cv_folds,
        "cv_seed": args.cv_seed,
        "cv_acc": cv_acc,
        "acc": acc,
        "md_coef": float(coef_by_col["Multiplicative Depth"]),
        "r_md": float(corr[corr["Feature"] == NAMES["Multiplicative Depth"]]["Pearson r"].iloc[0]),
        "nonzero_names": [NAMES[c] for c in nonzero_cols],
        "spearman_pred": spearman_pred,
        "n_unique_measured": int(df["used_noise"].nunique()),
        "under_pct": float(d_all["underestimated (%)"]),
        "max_under": float(d_all["max underestimation (bits)"]),
        "n_under5": int(d_all["rows underestimated by > 5 bits"]),
        "n_exh": int(censored.sum()),
        "pct_md_le3": 100.0 * float((md_series <= 3).mean()),
        "n_md_ge7": int((md_series >= 7).sum()),
        "n_mp": int((df["multiply_plain"] != 0).sum()),
        "n_neg": int((df["negate"] != 0).sum()),
    }
    write_text(out / "exp1_results.md", build_report(ctx))
    written.append("exp1_results.md")

    meta = {
        "experiment": "experiment_1 (NNLS noise-estimator validation)",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": {"path": csv_rel, "sha256": ctx["csv_sha"], "rows": len(df), "rows_budget_exhausted": int(censored.sum())},
        "noise_budget_constant": NOISE_BUDGET,
        "features_model_order": MODEL_COLUMNS,
        "model": "LinearRegression(fit_intercept=False, positive=True), fitted on all rows (as RL/pytrs/noise_estimator.py)",
        "supplementary_cv": {"folds": args.cv_folds, "seed": args.cv_seed, "note": "choice made for this reproduction; not in repo code"},
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit-learn": sklearn.__version__,
            "scipy": scipy.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "repo_sources_sha256_lf_normalised": repo_source_hashes(),
        "repo_estimator_check": repo_check,
        "outputs": written + ["run_metadata.json"],
    }
    write_text(out / "run_metadata.json", json.dumps(meta, indent=2) + "\n")

    print("[1B] coefficients: " + ", ".join(f"{NAMES[c]}={coef_by_col[c]:.6f}" for c in REPORT_ORDER))
    print("[1C] MAE=%.6f MSE=%.6f RMSE=%.6f R2=%.6f" % (acc["MAE"], acc["MSE"], acc["RMSE"], acc["R2"]))
    print("[done] outputs written to " + str(out))
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    args = parse_args(argv)
    try:
        return run(args)
    except DataError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
