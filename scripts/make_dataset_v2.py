"""Produce dataset v2 ("cleaned release") from the raw Kaggle export.

v2 applies the data-owner fixes that `validate` flags on v1:
  * drop customers with no CREDIT_LIMIT (1 row)
  * drop customers whose CASH_ADVANCE_FREQUENCY is > 1, which is impossible for a ratio (8 rows)

Rows are removed by copying the original text lines, so every kept row stays
byte-identical to v1 (a pandas round-trip would reformat numbers such as
`1000` -> `1000.0` and change the whole file, not just the bad rows).

Usage:  python scripts/make_dataset_v2.py data/CC_GENERAL.csv   (rewrites the file in place)
"""
from __future__ import annotations

import sys

import pandas as pd

FREQ = ["BALANCE_FREQUENCY", "PURCHASES_FREQUENCY", "ONEOFF_PURCHASES_FREQUENCY",
        "PURCHASES_INSTALLMENTS_FREQUENCY", "CASH_ADVANCE_FREQUENCY", "PRC_FULL_PAYMENT"]


def clean(df: pd.DataFrame) -> pd.DataFrame:
    bad_freq = ((df[FREQ] < 0) | (df[FREQ] > 1)).any(axis=1)
    no_limit = df["CREDIT_LIMIT"].isna()
    return df.loc[~(bad_freq | no_limit)].reset_index(drop=True)


if __name__ == "__main__":
    path = sys.argv[1]
    df = pd.read_csv(path)
    keep = set(clean(df)["CUST_ID"])
    with open(path, newline="") as fh:
        header, *lines = fh.readlines()
    kept = [ln for ln in lines if ln.split(",", 1)[0] in keep]
    with open(path, "w", newline="") as fh:
        fh.writelines([header, *kept])
    print(f"v2: {len(lines)} -> {len(kept)} rows ({len(lines) - len(kept)} removed)")
