#!/usr/bin/env python3
"""Promote a reviewed Football-Data download into immutable live-season lineage."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path

import pandas as pd

import run_data_audit as audit


SOURCE_URL = "https://www.football-data.co.uk/mmz4281/2627/T1.csv"


class PromotionError(RuntimeError):
    """A downloaded candidate is not safe to promote."""


def promote(args: argparse.Namespace) -> dict[str, object]:
    source = Path(args.input).resolve()
    if not source.is_file():
        raise PromotionError(f"input snapshot does not exist: {source}")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.artifact_digest):
        raise PromotionError("artifact_digest must be sha256:<64 lowercase hex characters>")
    if not args.acquisition_run_url.startswith("https://github.com/"):
        raise PromotionError("acquisition_run_url must be a GitHub HTTPS URL")

    with source.open("rb") as handle:
        audit.validate_download_bytes(handle.read(4096), SOURCE_URL)
    candidate_header = audit.raw_header(source)
    candidate = pd.read_csv(source, encoding="utf-8-sig", low_memory=False)
    missing_core = [column for column in audit.MINIMUM_SOURCE_COLUMNS if column not in candidate]
    if missing_core:
        raise PromotionError(f"candidate is missing core columns: {missing_core}")

    catalog = audit.load_current_snapshot_catalog()
    active = catalog.iloc[-1]
    active_path = (audit.ROOT / str(active["raw_path"])).resolve()
    active_header = audit.raw_header(active_path)
    if candidate_header != active_header:
        added = sorted(set(candidate_header) - set(active_header))
        removed = sorted(set(active_header) - set(candidate_header))
        raise PromotionError(
            "candidate schema changed; review and update the schema contract explicitly. "
            f"added={added}; removed={removed}"
        )

    dates = audit.parse_dates(candidate["Date"])
    if dates.isna().any():
        raise PromotionError("candidate contains date parsing failures")
    match_key = pd.DataFrame(
        {
            "date": dates.dt.strftime("%Y-%m-%d"),
            "home_team": candidate["HomeTeam"].astype("string").str.strip(),
            "away_team": candidate["AwayTeam"].astype("string").str.strip(),
        }
    )
    if match_key.isna().any(axis=None) or match_key.eq("").any(axis=None):
        raise PromotionError("candidate contains invalid team keys")
    if match_key.duplicated().any():
        raise PromotionError("candidate contains duplicate match keys")
    if candidate[["FTHG", "FTAG", "FTR"]].isna().any(axis=None):
        raise PromotionError("candidate contains incomplete full-time results")

    captured_at = pd.Timestamp(args.captured_at)
    if captured_at.tzinfo is None:
        raise PromotionError("captured_at must include an explicit timezone offset")
    captured_at = captured_at.tz_convert("UTC")
    previous_capture = pd.Timestamp(active["captured_at"])
    if captured_at <= previous_capture:
        raise PromotionError("captured_at must be later than the active snapshot")

    date_min = dates.min().date().isoformat()
    date_max = dates.max().date().isoformat()
    required_through = pd.Timestamp(args.required_through)
    if required_through.tzinfo is not None or required_through != required_through.normalize():
        raise PromotionError("required_through must be a timezone-free YYYY-MM-DD date")
    if pd.Timestamp(date_max) < required_through:
        raise PromotionError(
            f"candidate ends at {date_max}; required coverage is through "
            f"{required_through.date().isoformat()}"
        )
    if len(candidate) < int(active["row_count"]):
        raise PromotionError("candidate row count regressed; explicit source review is required")
    if pd.Timestamp(date_max) < pd.Timestamp(active["date_max"]):
        raise PromotionError("candidate maximum match date regressed")

    raw_bytes = source.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    captured_text = captured_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    captured_slug = captured_at.strftime("%Y%m%dT%H%M%SZ")
    snapshot_id = f"{captured_slug}_{digest[:12]}"
    relative_path = (
        Path("data/raw/football_data")
        / f"{audit.CURRENT_SEASON}__{captured_slug}__{digest[:12]}.csv"
    )
    target = (audit.ROOT / relative_path).resolve()
    if not target.is_relative_to(audit.RAW_DIR.resolve()):
        raise PromotionError("computed target escaped the raw-data directory")
    if target.exists():
        raise PromotionError(f"refusing to overwrite existing raw snapshot: {target}")

    new_row = pd.DataFrame(
        [
            {
                "season": audit.CURRENT_SEASON,
                "snapshot_id": snapshot_id,
                "raw_path": relative_path.as_posix(),
                "source_url": SOURCE_URL,
                "captured_at": captured_text,
                "acquisition_run_url": args.acquisition_run_url,
                "artifact_name": args.artifact_name,
                "artifact_digest": args.artifact_digest,
                "sha256": digest,
                "bytes": len(raw_bytes),
                "row_count": len(candidate),
                "date_min": date_min,
                "date_max": date_max,
            }
        ],
        columns=audit.CURRENT_SNAPSHOT_COLUMNS,
    )
    updated = pd.concat([catalog, new_row], ignore_index=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        suffix=".tmp",
        dir=audit.CURRENT_SNAPSHOT_CATALOG.parent,
        delete=False,
    ) as handle:
        catalog_temp = Path(handle.name)
        updated.to_csv(handle, index=False, lineterminator="\n")

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as handle:
            handle.write(raw_bytes)
        os.replace(catalog_temp, audit.CURRENT_SNAPSHOT_CATALOG)
    except OSError:
        if catalog_temp.exists():
            catalog_temp.unlink()
        if target.exists() and audit.sha256_file(target) == digest:
            target.unlink()
        raise
    audit.load_current_snapshot_catalog()

    return {
        "snapshot_id": snapshot_id,
        "raw_path": relative_path.as_posix(),
        "sha256": digest,
        "row_count": len(candidate),
        "date_max": date_max,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and immutably register a current-season CSV artifact."
    )
    parser.add_argument("--input", required=True, help="Downloaded 2026-27 CSV path.")
    parser.add_argument("--captured-at", required=True, help="Timezone-aware acquisition time.")
    parser.add_argument("--required-through", required=True, help="Latest completed match date.")
    parser.add_argument("--acquisition-run-url", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-digest", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = promote(args)
        print(
            "PROMOTED CURRENT SNAPSHOT: "
            f"{result['snapshot_id']}; {result['row_count']} rows; "
            f"covers through {result['date_max']}; {result['raw_path']}"
        )
        print("Next: python scripts/run_data_foundation.py")
        return 0
    except (audit.AuditError, PromotionError, OSError, ValueError) as exc:
        print(f"SNAPSHOT PROMOTION FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
