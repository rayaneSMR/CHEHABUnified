"""Merge the per-budget evaluation files of each dataset into one Excel file.

    python scripts/merge_eval_results.py RL/test_results

Reads every eval_<dataset>_b<budget>_<jobid>.xlsx written by eval_unified_sweep.sbatch
and writes eval_<dataset>_ALL.xlsx with the same sheets (all_results, summary_per_budget,
summary_per_pref, front_metrics, front_summary, feasible_summary, infeasible_summary),
the rows of every budget stacked and sorted by budget. If a dataset was evaluated more
than once at the same budget, only the newest file (highest job id) is used.
"""
import re
import sys
from pathlib import Path

import pandas as pd

# Optional _agent<budget>: runs where the agent got another budget than the test budget
# (e.g. eval_threshold_benchmarks_b230_agent9000000_<job>.xlsx, the unconstrained baseline).
# They are merged into their own file, eval_<dataset>_agent<budget>_ALL.xlsx.
PATTERN = re.compile(r"^eval_(?P<tag>.+)_b(?P<budget>\d+)(?P<agent>_agent\d+)?_(?P<job>[^_]+)\.xlsx$")
SHEETS = ["all_results", "summary_per_budget", "summary_per_pref", "front_metrics",
          "front_summary", "feasible_summary", "infeasible_summary"]


def _job_key(job):
    return int(job) if job.isdigit() else -1


def main(folder):
    folder = Path(folder)
    newest = {}   # (tag, budget) -> (job, path)
    for path in folder.glob("eval_*_b*_*.xlsx"):
        m = PATTERN.match(path.name)
        if not m or path.name.endswith("_ALL.xlsx"):
            continue
        key = (m["tag"] + (m["agent"] or ""), int(m["budget"]))
        if key not in newest or _job_key(m["job"]) > _job_key(newest[key][0]):
            newest[key] = (m["job"], path)

    if not newest:
        print(f"No eval_<dataset>_b<budget>_<jobid>.xlsx files in {folder}")
        return

    for tag in sorted({t for t, _ in newest}):
        files = sorted((b, p) for (t, b), (_, p) in newest.items() if t == tag)
        out = folder / f"eval_{tag}_ALL.xlsx"
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            for sheet in SHEETS:
                parts = []
                for _, p in files:
                    try:
                        parts.append(pd.read_excel(p, sheet_name=sheet))
                    except ValueError:      # sheet missing in this file (e.g. no infeasible rows)
                        pass
                if parts:
                    df = pd.concat(parts, ignore_index=True)
                    if "Budget" in df.columns:
                        df = df.sort_values("Budget", kind="stable")
                    df.to_excel(writer, sheet_name=sheet, index=False)
        print(f"{out}  <-  budgets {[b for b, _ in files]}")


E2E_MEANS = ["circuit_execution_time (s)", "total_execution_time (s)", "galois_keys_generation_time (s)",
             "rotation_keys_size (MB)", "Remaining_noise_budget", "peak_ram (MB)", "rotate_rows",
             "multiply", "multiply_plain", "Depth", "Multiplicative Depth", "compile_time (s)",
             "safe_keys", "safe_ops"]


# Front metrics, same formulas as RL/fhe_rl/unified_bisection.py (copied so this script
# does not need to import the RL package).
HV_REF = (1.1, 1.1)
EU_PREFS = [[round(1.0 - i / 10, 1), round(i / 10, 1)] for i in range(10)]


def _front(pts):
    """Non-dominated (x, y) points (both minimized), deduplicated, sorted by x."""
    pts = sorted(set(pts))
    return [p for p in pts if not any(q[0] <= p[0] and q[1] <= p[1] and q != p for q in pts)]


def _hypervolume(pts, ref=HV_REF):
    hv, prev = 0.0, ref[1]
    for x, y in sorted(pts):
        if x < ref[0] and y < prev:
            hv += (ref[0] - x) * (prev - y)
            prev = y
    return hv


def _sparsity(pts):
    if len(pts) < 2:
        return 0.0
    pts = sorted(pts)
    return sum((pts[i][0] - pts[i + 1][0]) ** 2 + (pts[i][1] - pts[i + 1][1]) ** 2
               for i in range(len(pts) - 1)) / (len(pts) - 1)


def _expected_utility(pts):
    return sum(max(-(w[0] * x + w[1] * y) for x, y in pts) for w in EU_PREFS) / len(EU_PREFS)


def e2e_front_metrics(ok):
    """Per (benchmark, budget): IC / HV / SP / EU over the preferences, on
    (C_exec, C_keys) normalized by the input expression, and on the measured
    (execution time, rotation key MB) normalized by the largest value of the config."""
    rows = []
    for (bench, budget), g in ok.groupby(["benchmark", "budget"], sort=True):
        row = {"benchmark": bench, "budget": budget, "Preferences OK": len(g)}
        ops0 = pd.to_numeric(g["initial_ops"], errors="coerce").max()
        keys0 = pd.to_numeric(g["initial_keys"], errors="coerce").max()
        cost_pts = [(o / ops0 if ops0 else o, k / max(keys0, 1))
                    for o, k in zip(pd.to_numeric(g["safe_ops"], errors="coerce"),
                                    pd.to_numeric(g["safe_keys"], errors="coerce"))
                    if pd.notna(o) and pd.notna(k)]
        t = pd.to_numeric(g["circuit_execution_time (s)"], errors="coerce")
        m = pd.to_numeric(g["rotation_keys_size (MB)"], errors="coerce")
        t_max, m_max = t.max(), m.max()
        real_pts = [(ti / t_max if t_max else ti, mi / m_max if m_max else mi)
                    for ti, mi in zip(t, m) if pd.notna(ti) and pd.notna(mi)]
        for tag, pts in (("Cost", cost_pts), ("Measured", real_pts)):
            front = _front(pts)
            row[f"{tag} IC"] = len(front)
            row[f"{tag} HV"] = round(_hypervolume(front), 6) if front else None
            row[f"{tag} SP"] = round(_sparsity(front), 6) if front else None
            row[f"{tag} EU"] = round(_expected_utility(front), 6) if front else None
        rows.append(row)
    return pd.DataFrame(rows)


def merge_e2e(folder):
    """Real compile + SEAL runs (e2e_<benchmarks>_b<budget>_<jobid>.csv) -> e2e_ALL.xlsx."""
    files = sorted(f for f in Path(folder).glob("e2e_*_b*_*.csv") if not f.name.startswith("e2e_original_"))
    if not files:
        return
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    # Keep the newest row per (benchmark, budget, preference) if a run was repeated
    df = df.drop_duplicates(["benchmark", "budget", "w_ops"], keep="last")
    ok = df[df["status"] == "ok"]

    def summarize(keys):
        rows = []
        for k, g in df.groupby(keys, sort=True):
            gok = ok.loc[ok.index.intersection(g.index)]
            r = dict(zip(keys, k if isinstance(k, tuple) else (k,)))
            r["Runs"] = len(g)
            r["OK"] = len(gok)
            r["Outputs Correct"] = int((gok["outputs_match"] == True).sum())   # noqa: E712
            r["Rollback Rate (%)"] = round(pd.to_numeric(g["safety_activated"].map(
                {True: 1, False: 0, "True": 1, "False": 0}), errors="coerce").mean() * 100, 1)
            for c in E2E_MEANS:
                if c in gok:
                    r[f"Avg {c}"] = round(pd.to_numeric(gok[c], errors="coerce").mean(), 4)
            rows.append(r)
        return pd.DataFrame(rows)

    out = Path(folder) / "e2e_ALL.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.sort_values(["budget", "benchmark", "w_ops"], ascending=[True, True, False]).to_excel(
            writer, sheet_name="all_runs", index=False)
        summarize(["budget", "w_ops", "w_keys"]).to_excel(writer, sheet_name="summary_per_pref", index=False)
        summarize(["benchmark", "budget"]).to_excel(writer, sheet_name="summary_per_benchmark", index=False)
        if len(ok):
            fm = e2e_front_metrics(ok)
            fm.to_excel(writer, sheet_name="front_metrics", index=False)
            fm.drop(columns=["benchmark"]).groupby("budget").mean(numeric_only=True).round(4).reset_index() \
              .to_excel(writer, sheet_name="front_summary", index=False)
    print(f"{out}  <-  {len(files)} real compile + SEAL files, {len(df)} runs ({len(ok)} ok)")


def merge_e2e_original(folder):
    """Original CHEHAB RL agent (e2e_original_<benchmarks>_<jobid>.csv) -> e2e_original_ALL.xlsx.
    One run per benchmark; if a benchmark was rerun, the newest job is kept."""
    files = sorted(Path(folder).glob("e2e_original_*.csv"),
                   key=lambda f: _job_key(f.stem.rsplit("_", 1)[-1]))
    if not files:
        return
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = df.drop_duplicates(["benchmark"], keep="last").sort_values("benchmark")
    ok = df[df["status"] == "ok"]
    summary = pd.DataFrame([{
        "Benchmarks": len(df),
        "OK": len(ok),
        "Outputs Correct": int((ok["outputs_match"] == True).sum()),   # noqa: E712
        "Outputs Wrong": int((ok["outputs_match"] == False).sum()),    # noqa: E712
        "No Reference": int(ok["outputs_match"].isna().sum()),
        "Avg circuit_execution_time (s)": round(pd.to_numeric(ok["circuit_execution_time (s)"], errors="coerce").mean(), 4),
    }])
    out = Path(folder) / "e2e_original_ALL.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="all_runs", index=False)
        summary.to_excel(writer, sheet_name="summary", index=False)
    print(f"{out}  <-  {len(files)} files, {len(df)} benchmarks ({len(ok)} ok)")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "RL/test_results"
    main(target)
    merge_e2e(target)
    merge_e2e_original(target)
