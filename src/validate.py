"""Stage 1 - validate the raw snapshot before anything is trained on it.

Hard failures (wrong schema, too few rows, too many nulls, duplicate IDs)
stop the pipeline. Soft issues (e.g. out-of-range frequencies) are counted
and reported as metrics so they can be compared across data versions.
"""
from __future__ import annotations

import sys

import pandas as pd

from common import EXPECTED_COLUMNS, FREQUENCY_COLUMNS, ROOT, get_logger, load_params, write_json

log = get_logger("validate")


def validate(df: pd.DataFrame, max_null_fraction: float, min_rows: int, id_column: str) -> dict:
    errors: list[str] = []

    missing = sorted(set(EXPECTED_COLUMNS) - set(df.columns))
    extra = sorted(set(df.columns) - set(EXPECTED_COLUMNS))
    if missing:
        errors.append(f"missing columns: {missing}")
    if len(df) < min_rows:
        errors.append(f"only {len(df)} rows (< {min_rows})")

    null_fraction = df.isna().mean()
    too_many_nulls = null_fraction[null_fraction > max_null_fraction]
    for col, frac in too_many_nulls.items():
        errors.append(f"{col} is {frac:.1%} null (> {max_null_fraction:.0%})")

    duplicate_ids = int(df[id_column].duplicated().sum()) if id_column in df else 0
    if duplicate_ids:
        errors.append(f"{duplicate_ids} duplicate {id_column} values")

    out_of_range = {
        col: int(((df[col] < 0) | (df[col] > 1)).sum())
        for col in FREQUENCY_COLUMNS if col in df
    }
    numeric = df.select_dtypes("number")
    negative_values = int((numeric < 0).sum().sum())

    return {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "unexpected_columns": extra,
        "null_cells": int(df.isna().sum().sum()),
        "rows_with_nulls": int(df.isna().any(axis=1).sum()),
        "null_fraction": {c: round(float(v), 5) for c, v in null_fraction.items() if v > 0},
        "duplicate_ids": duplicate_ids,
        "frequency_out_of_range": int(sum(out_of_range.values())),
        "frequency_out_of_range_by_column": {c: n for c, n in out_of_range.items() if n},
        "negative_values": negative_values,
        "errors": errors,
        "passed": not errors,
    }


def main() -> None:
    data_p = load_params("data")
    p = load_params("validate")
    df = pd.read_csv(ROOT / data_p["raw_path"])
    report = validate(df, p["max_null_fraction"], p["min_rows"], data_p["id_column"])
    write_json(report, "metrics/validation.json")
    log.info("rows=%d nulls=%d out_of_range=%d passed=%s",
             report["rows"], report["null_cells"], report["frequency_out_of_range"], report["passed"])
    if not report["passed"]:
        for err in report["errors"]:
            log.error(err)
        sys.exit(1)


if __name__ == "__main__":
    main()
