"""Unit tests for the pure pipeline functions (no DVC / network needed)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from common import EXPECTED_COLUMNS  # noqa: E402
from make_dataset_v2 import clean  # noqa: E402
from preprocess import build_features  # noqa: E402
from validate import validate  # noqa: E402


@pytest.fixture
def frame():
    rng = np.random.default_rng(0)
    n = 50
    df = pd.DataFrame(rng.uniform(0, 1, size=(n, len(EXPECTED_COLUMNS) - 1)),
                      columns=EXPECTED_COLUMNS[1:])
    df.insert(0, "CUST_ID", [f"C{i}" for i in range(n)])
    return df


PRE = {"impute_strategy": "median", "log_transform": True, "clip_quantile": 0.99, "scaler": "standard"}


def test_validate_passes_clean_frame(frame):
    report = validate(frame, max_null_fraction=0.05, min_rows=10, id_column="CUST_ID")
    assert report["passed"] and report["errors"] == []


def test_validate_catches_schema_nulls_and_duplicates(frame):
    bad = frame.drop(columns=["TENURE"])
    bad.loc[:10, "BALANCE"] = np.nan
    bad.loc[1, "CUST_ID"] = bad.loc[0, "CUST_ID"]
    report = validate(bad, max_null_fraction=0.05, min_rows=10, id_column="CUST_ID")
    assert not report["passed"]
    joined = " ".join(report["errors"])
    assert "missing columns" in joined and "BALANCE" in joined and "duplicate" in joined


def test_validate_counts_out_of_range_frequency(frame):
    frame.loc[0, "CASH_ADVANCE_FREQUENCY"] = 1.5
    report = validate(frame, max_null_fraction=0.05, min_rows=10, id_column="CUST_ID")
    assert report["passed"]  # soft issue only
    assert report["frequency_out_of_range"] == 1


@pytest.mark.parametrize("scaler", ["standard", "robust", "minmax"])
def test_build_features_has_no_nans_and_keeps_ids(frame, scaler):
    frame.loc[0, "MINIMUM_PAYMENTS"] = np.nan
    feats, _ = build_features(frame, {**PRE, "scaler": scaler}, "CUST_ID")
    assert not feats.isna().any().any()
    assert list(feats.index) == list(frame["CUST_ID"])
    assert "CUST_ID" not in feats.columns


def test_build_features_clips_frequencies(frame):
    frame.loc[0, "CASH_ADVANCE_FREQUENCY"] = 1.5
    feats, scaler = build_features(frame, {**PRE, "scaler": "minmax"}, "CUST_ID")
    col = list(feats.columns).index("CASH_ADVANCE_FREQUENCY")
    assert scaler.data_max_[col] <= 1.0


def test_clean_drops_invalid_rows(frame):
    frame.loc[0, "CREDIT_LIMIT"] = np.nan
    frame.loc[1, "CASH_ADVANCE_FREQUENCY"] = 1.5
    out = clean(frame)
    assert len(out) == len(frame) - 2
    assert {"C0", "C1"}.isdisjoint(out["CUST_ID"])
