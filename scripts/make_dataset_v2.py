"""Produce dataset v2 ("cleaned release") from the raw Kaggle export.

v2 applies the data-owner fixes that `validate` flags on v1:
  * drop customers with no CREDIT_LIMIT (1 row)
  * drop customers whose CASH_ADVANCE_FREQUENCY is > 1, which is impossible for a ratio (8 rows)

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
    out = clean(df)
    out.to_csv(path, index=False)
    print(f"v2: {len(df)} -> {len(out)} rows ({len(df) - len(out)} removed)")
