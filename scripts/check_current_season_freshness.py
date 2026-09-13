#!/usr/bin/env python3
"""Fail closed when the active live-season snapshot is too old or incomplete."""

from __future__ import annotations

import argparse
import sys

import pandas as pd

import run_data_audit as audit


class FreshnessError(RuntimeError):
    """The live snapshot is unsafe for the requested prediction boundary."""


def validate_freshness(
    *, as_of: str, required_through: str, max_capture_age_hours: float
) -> dict[str, object]:
    if max_capture_age_hours <= 0:
        raise FreshnessError("max_capture_age_hours must be positive")

    prediction_time = pd.Timestamp(as_of)
    if prediction_time.tzinfo is None:
        raise FreshnessError("as_of must include an explicit timezone offset")
    prediction_time = prediction_time.tz_convert("UTC")

    coverage_date = pd.Timestamp(required_through)
    if coverage_date.tzinfo is not None:
        raise FreshnessError("required_through must be a calendar date without a timezone")
    if coverage_date != coverage_date.normalize():
        raise FreshnessError("required_through must not contain a time")

    snapshot = audit.active_current_snapshot()
    captured_at = pd.Timestamp(snapshot["captured_at"])
    if captured_at > prediction_time:
        raise FreshnessError("active snapshot was captured after the prediction time")
    capture_age_hours = (prediction_time - captured_at).total_seconds() / 3600
    if capture_age_hours > max_capture_age_hours:
        raise FreshnessError(
            f"active snapshot is {capture_age_hours:.2f} hours old; "
            f"maximum is {max_capture_age_hours:.2f}"
        )

    snapshot_date_max = pd.Timestamp(snapshot["date_max"])
    if snapshot_date_max < coverage_date:
        raise FreshnessError(
            f"active snapshot ends at {snapshot['date_max']}; "
            f"required coverage is through {coverage_date.date().isoformat()}"
        )

    return {
        "snapshot_id": snapshot["snapshot_id"],
        "captured_at": snapshot["captured_at"],
        "capture_age_hours": capture_age_hours,
        "date_max": snapshot["date_max"],
        "required_through": coverage_date.date().isoformat(),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate live snapshot age and completed-match coverage."
    )
    parser.add_argument(
        "--as-of",
        required=True,
        help="Timezone-aware prediction timestamp, for example 2026-09-14T20:00:00+03:00.",
    )
    parser.add_argument(
        "--required-through",
        required=True,
        help="Latest calendar match date that must be included (YYYY-MM-DD).",
    )
    parser.add_argument("--max-capture-age-hours", type=float, default=24.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = validate_freshness(
            as_of=args.as_of,
            required_through=args.required_through,
            max_capture_age_hours=args.max_capture_age_hours,
        )
        print(
            "LIVE SNAPSHOT READY: "
            f"{result['snapshot_id']}; captured {result['captured_at']}; "
            f"covers through {result['date_max']}."
        )
        return 0
    except (audit.AuditError, FreshnessError, ValueError) as exc:
        print(f"LIVE SNAPSHOT NOT READY: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
