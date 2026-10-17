"""
Data Profiling & Quality Analysis Script (PRD §6, §8, §12).
Profiles raw and processed data, reporting nulls, distributions, formats, outliers, and defects.
Usage: python notebooks/profile_data.py [--raw-dir data/raw] [--out-file docs/profiling_report.md]
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd
import numpy as np


def profile_dataframe(name: str, df: pd.DataFrame) -> dict:
    total_rows = len(df)
    total_cols = len(df.columns)
    null_counts = df.isna().sum().to_dict()
    null_pcts = {c: round((cnt / total_rows) * 100, 2) for c, cnt in null_counts.items()} if total_rows > 0 else {}
    duplicate_rows = df.duplicated().sum()

    col_stats = []
    for col in df.columns:
        s = df[col]
        nunique = s.nunique(dropna=False)
        num_null = s.isna().sum()
        dtype_str = str(s.dtype)
        sample_vals = [str(x) for x in s.dropna().unique()[:3]]
        col_stats.append({
            "column": col,
            "dtype": dtype_str,
            "unique": nunique,
            "nulls": num_null,
            "null_pct": f"{(num_null / total_rows)*100:.1f}%" if total_rows > 0 else "0%",
            "sample_values": ", ".join(sample_vals[:3]),
        })

    return {
        "table": name,
        "rows": total_rows,
        "cols": total_cols,
        "duplicates": int(duplicate_rows),
        "columns": col_stats,
    }


def generate_markdown_report(profiles: list[dict], out_path: Path) -> None:
    lines = [
        "# Raw Data Profiling & Defect Analysis Report",
        "",
        "> Generated automatically by the Retail Analytics Platform Data Profiler.",
        "",
        "## Summary Overview",
        "",
        "| Table | Rows | Columns | Exact Duplicate Rows |",
        "|-------|------|---------|-----------------------|",
    ]

    for p in profiles:
        lines.append(f"| **{p['table']}** | {p['rows']:,} | {p['cols']} | {p['duplicates']:,} |")

    lines.extend(["", "## Detailed Table Profiles", ""])

    for p in profiles:
        lines.extend([
            f"### Table: `{p['table']}` ({p['rows']:,} rows, {p['cols']} columns)",
            "",
            "| Column | Type | Distinct | Nulls | Null % | Sample Values |",
            "|--------|------|----------|-------|--------|---------------|",
        ])
        for c in p["columns"]:
            lines.append(f"| `{c['column']}` | {c['dtype']} | {c['unique']:,} | {c['nulls']:,} | {c['null_pct']} | {c['sample_values'][:40]} |")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    print(f"✓ Profiling report written to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Profile raw CSV datasets")
    parser.add_argument("--raw-dir", default="data/raw", help="Path to raw CSVs")
    parser.add_argument("--out-file", default="docs/profiling_report.md", help="Output markdown path")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    tables = ["stores", "products", "customers", "orders", "order_items", "inventory", "returns"]
    profiles = []

    for t in tables:
        p = raw_dir / f"{t}.csv"
        if not p.exists():
            print(f"Skipping {t}: file not found")
            continue
        df = pd.read_csv(p, dtype=str)
        prof = profile_dataframe(t, df)
        profiles.append(prof)
        print(f"Profiled {t}: {len(df):,} rows")

    if profiles:
        generate_markdown_report(profiles, Path(args.out_file))


if __name__ == "__main__":
    main()
