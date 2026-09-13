#!/usr/bin/env python3
"""Shared chronological boundary helpers; contains no predictive model."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from pandas.api.types import is_bool_dtype


class TimelineError(ValueError):
    """A timestamp or eligibility value violates the evaluation contract."""


def _prediction_time_utc(value: str | datetime | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise TimelineError("Prediction time must include an explicit timezone")
    return timestamp.tz_convert("UTC")


def _model_eligibility(values: pd.Series) -> pd.Series:
    if is_bool_dtype(values.dtype):
        return values.astype(bool)
    normalized = values.astype("string").str.strip().str.lower().map(
        {"true": True, "false": False}
    )
    if normalized.isna().any():
        raise TimelineError("model_eligible contains invalid or missing values")
    return normalized.astype(bool)


def available_history(
    matches: pd.DataFrame,
    prediction_time: str | datetime | pd.Timestamp,
) -> pd.DataFrame:
    """Return eligible rows whose result was available strictly before prediction."""
    required = {"model_eligible", "result_available_at"}
    missing = required.difference(matches.columns)
    if missing:
        raise TimelineError(f"Match data is missing timeline columns: {sorted(missing)}")

    cutoff = _prediction_time_utc(prediction_time)
    eligible = _model_eligibility(matches["model_eligible"])
    availability = pd.to_datetime(
        matches["result_available_at"], format="ISO8601", errors="coerce", utc=True
    )
    if availability.loc[eligible].isna().any():
        raise TimelineError("Eligible rows contain invalid result availability timestamps")

    visible = eligible & availability.notna() & availability.lt(cutoff)
    return matches.loc[visible].copy()


__all__ = ["TimelineError", "available_history"]
