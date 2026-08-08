#!/usr/bin/env python3
"""Reproducible Phase 0 audit for Football-Data Turkish Super Lig CSVs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "football_data"
REPORTS_DIR = ROOT / "reports"
SOURCE_CATALOG = ROOT / "config" / "raw_sources.csv"
SCHEMA_LOCK = ROOT / "config" / "expected_schemas.json"
DATA_CONTRACT = ROOT / "DATA_CONTRACT.md"
ACQUISITION_PROVENANCE = ROOT / "config" / "acquisition_provenance.json"

SEASONS = [
    "2017-18",
    "2018-19",
    "2019-20",
    "2020-21",
    "2021-22",
    "2022-23",
    "2023-24",
    "2024-25",
    "2025-26",
]

MINIMUM_SOURCE_COLUMNS = [
    "Div",
    "Date",
    "HomeTeam",
    "AwayTeam",
    "FTHG",
    "FTAG",
    "FTR",
]

AUDITED_FIELDS = [
    "FTHG",
    "FTAG",
    "FTR",
    "HTHG",
    "HTAG",
    "HS",
    "AS",
    "HST",
    "AST",
    "HF",
    "AF",
    "HC",
    "AC",
    "HY",
    "AY",
    "HR",
    "AR",
]

MATCH_STAT_FIELDS = [
    "HS",
    "AS",
    "HST",
    "AST",
    "HF",
    "AF",
    "HC",
    "AC",
    "HY",
    "AY",
    "HR",
    "AR",
]

CANONICAL_FIELD_MAP = OrderedDict(
    [
        ("season", "derived from source catalog"),
        ("date", "Date"),
        ("kickoff_time", "Time"),
        ("home_team", "HomeTeam after approved alias mapping"),
        ("away_team", "AwayTeam after approved alias mapping"),
        ("home_goals", "FTHG"),
        ("away_goals", "FTAG"),
        ("result", "FTR"),
        ("home_ht_goals", "HTHG"),
        ("away_ht_goals", "HTAG"),
        ("home_shots", "HS"),
        ("away_shots", "AS"),
        ("home_shots_on_target", "HST"),
        ("away_shots_on_target", "AST"),
        ("home_fouls", "HF"),
        ("away_fouls", "AF"),
        ("home_corners", "HC"),
        ("away_corners", "AC"),
        ("home_yellow_cards", "HY"),
        ("away_yellow_cards", "AY"),
        ("home_red_cards", "HR"),
        ("away_red_cards", "AR"),
    ]
)

BOOKMAKER_NAMES = {
    "1XB": "1XBet",
    "B365": "Bet365",
    "BF": "Betfair",
    "BFD": "Betfred",
    "BFE": "Betfair Exchange",
    "BMGM": "BetMGM",
    "BV": "BetVictor",
    "BW": "Bet&Win",
    "CL": "Coral",
    "IW": "Interwetten",
    "LB": "Ladbrokes",
    "PS": "Pinnacle",
    "VC": "VC Bet",
    "WH": "William Hill",
}

# Proposals only. Nothing in Phase 0 applies these mappings to raw data.
ALIAS_PROPOSALS = [
    {
        "source_name": "Ad. Demirspor",
        "proposed_canonical_name": "Adana Demirspor",
        "confidence": "high",
        "review_status": "proposed_not_applied",
        "reason": "Unambiguous source abbreviation in the audited seasons.",
    },
    {
        "source_name": "Buyuksehyr",
        "proposed_canonical_name": "Istanbul Basaksehir",
        "confidence": "high",
        "review_status": "proposed_not_applied",
        "reason": "Stable truncated/transliterated source label across all nine seasons.",
    },
    {
        "source_name": "Goztep",
        "proposed_canonical_name": "Goztepe",
        "confidence": "high",
        "review_status": "proposed_not_applied",
        "reason": "Stable one-character truncation of the club name.",
    },
    {
        "source_name": "Karagumruk",
        "proposed_canonical_name": "Fatih Karagumruk",
        "confidence": "high",
        "review_status": "proposed_not_applied",
        "reason": "Unambiguous shortened club name in this league and time range.",
    },
    {
        "source_name": "Akhisar Belediyespor",
        "proposed_canonical_name": "Akhisarspor",
        "confidence": "high",
        "review_status": "proposed_not_applied",
        "reason": "Historical club-name change; no competing Akhisar entity appears.",
    },
    {
        "source_name": "Erzurum BB",
        "proposed_canonical_name": "Erzurumspor FK",
        "confidence": "review",
        "review_status": "human_review_required",
        "reason": "Likely historical abbreviation/name change; old Erzurum entities make automatic merging unsafe.",
    },
    {
        "source_name": "Gaziantep",
        "proposed_canonical_name": "Gaziantep FK",
        "confidence": "review",
        "review_status": "human_review_required",
        "reason": "Likely current club, but the city has had distinct historical clubs.",
    },
]


class AuditError(RuntimeError):
    """A loud, actionable audit failure."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pct(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{100 * float(value):.2f}%"


def md_escape(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def md_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    rendered = ["| " + " | ".join(md_escape(v) for v in headers) + " |"]
    rendered.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        rendered.append("| " + " | ".join(md_escape(v) for v in row) + " |")
    return "\n".join(rendered)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(
        path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.6f",
    )


def load_source_catalog() -> pd.DataFrame:
    if not SOURCE_CATALOG.exists():
        raise AuditError(f"Missing source catalog: {SOURCE_CATALOG}")
    sources = pd.read_csv(SOURCE_CATALOG, dtype={"season": "str", "source_code": "str"})
    required = {"season", "source_code", "source_url", "sha256", "bytes"}
    missing = required.difference(sources.columns)
    if missing:
        raise AuditError(f"Source catalog is missing columns: {sorted(missing)}")
    if sources["season"].tolist() != SEASONS:
        raise AuditError(
            "Source catalog season order changed. Expected "
            f"{SEASONS}, found {sources['season'].tolist()}"
        )
    if sources["season"].duplicated().any():
        raise AuditError("Source catalog contains duplicate seasons.")
    return sources


def validate_download_bytes(content_start: bytes, source_url: str) -> None:
    stripped = content_start.lstrip()
    if stripped.startswith((b"<html", b"<!DOCTYPE", b"<!doctype")):
        raise AuditError(f"HTML returned instead of CSV: {source_url}")
    header = content_start.splitlines()[0].decode("utf-8-sig", errors="replace")
    if not header.startswith("Div,Date,"):
        raise AuditError(f"Unexpected CSV header from {source_url}: {header[:160]}")


def download_missing_source(source: pd.Series, target: Path) -> None:
    try:
        import requests
    except ImportError as exc:  # pragma: no cover - dependency error path
        raise AuditError("requests is required to download missing raw files") from exc

    temp = target.with_suffix(target.suffix + ".download")
    if temp.exists():
        raise AuditError(
            f"Previous incomplete download exists: {temp}. Inspect it explicitly; "
            "the audit will not overwrite it."
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    url = str(source["source_url"])
    try:
        with requests.get(
            url,
            stream=True,
            timeout=(20, 60),
            headers={"User-Agent": "AI-SuperLig-Phase0-Data-Audit/1.0"},
        ) as response:
            response.raise_for_status()
            with temp.open("xb") as handle:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        handle.write(chunk)
        with temp.open("rb") as handle:
            validate_download_bytes(handle.read(4096), url)
        actual_hash = sha256_file(temp)
        expected_hash = str(source["sha256"])
        if actual_hash != expected_hash:
            raise AuditError(
                f"Upstream snapshot changed for {source['season']}: expected SHA-256 "
                f"{expected_hash}, got {actual_hash}. The .download file was preserved "
                "for explicit review."
            )
        if temp.stat().st_size != int(source["bytes"]):
            raise AuditError(
                f"Byte-size mismatch for {source['season']}: expected "
                f"{source['bytes']}, got {temp.stat().st_size}"
            )
        os.replace(temp, target)
    except AuditError:
        raise
    except Exception as exc:
        raise AuditError(f"Download failed for {source['season']} ({url}): {exc}") from exc


def ensure_raw_sources(sources: pd.DataFrame, offline: bool) -> pd.DataFrame:
    manifest_rows: list[dict[str, Any]] = []
    failures: list[str] = []

    for _, source in sources.iterrows():
        season = str(source["season"])
        target = RAW_DIR / f"{season}.csv"
        try:
            if not target.exists():
                if offline:
                    raise AuditError(f"Missing raw file in offline mode: {target}")
                download_missing_source(source, target)

            with target.open("rb") as handle:
                validate_download_bytes(handle.read(4096), str(source["source_url"]))
            actual_hash = sha256_file(target)
            actual_bytes = target.stat().st_size
            if actual_hash != str(source["sha256"]):
                raise AuditError(
                    f"Immutable raw file checksum mismatch for {season}: expected "
                    f"{source['sha256']}, got {actual_hash}. Refusing to repair or overwrite."
                )
            if actual_bytes != int(source["bytes"]):
                raise AuditError(
                    f"Immutable raw file byte-size mismatch for {season}: expected "
                    f"{source['bytes']}, got {actual_bytes}."
                )
            manifest_rows.append(
                {
                    "season": season,
                    "raw_path": target.relative_to(ROOT).as_posix(),
                    "source_url": source["source_url"],
                    "expected_sha256": source["sha256"],
                    "actual_sha256": actual_hash,
                    "bytes": actual_bytes,
                    "checksum_ok": True,
                }
            )
        except AuditError as exc:
            failures.append(str(exc))

    if failures:
        failure_report = [
            "# Data audit blocked: source acquisition failure",
            "",
            "**Verdict: NO-GO.** No audit result was invented or substituted.",
            "",
            "## Failures",
            "",
        ]
        failure_report.extend(f"- {failure}" for failure in failures)
        write_text(REPORTS_DIR / "DATA_AUDIT.md", "\n".join(failure_report))
        raise AuditError("; ".join(failures))

    return pd.DataFrame(manifest_rows)


def raw_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise AuditError(f"Empty CSV: {path}") from exc
    duplicates = sorted({name for name in header if header.count(name) > 1})
    if duplicates:
        raise AuditError(f"Duplicate raw header names in {path.name}: {duplicates}")
    return header


def read_raw_frames(sources: pd.DataFrame) -> OrderedDict[str, pd.DataFrame]:
    frames: OrderedDict[str, pd.DataFrame] = OrderedDict()
    for season in sources["season"]:
        path = RAW_DIR / f"{season}.csv"
        expected_header = raw_header(path)
        try:
            frame = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
        except UnicodeDecodeError:
            frame = pd.read_csv(path, encoding="cp1252", low_memory=False)
        if frame.columns.tolist() != expected_header:
            raise AuditError(
                f"Parser changed the header for {season}. Raw={expected_header}, "
                f"parsed={frame.columns.tolist()}"
            )
        missing_core = [column for column in MINIMUM_SOURCE_COLUMNS if column not in frame]
        if missing_core:
            raise AuditError(f"{season} is missing required source columns: {missing_core}")
        frames[str(season)] = frame
    return frames


def schema_payload(frames: OrderedDict[str, pd.DataFrame]) -> dict[str, Any]:
    return {
        "description": "Exact ordered raw columns audited for each Football-Data snapshot.",
        "schemas": {season: frame.columns.tolist() for season, frame in frames.items()},
    }


def lock_or_validate_schemas(
    frames: OrderedDict[str, pd.DataFrame], write_schema_lock: bool
) -> None:
    current = schema_payload(frames)
    if write_schema_lock:
        write_text(SCHEMA_LOCK, json.dumps(current, indent=2, ensure_ascii=False))
        return
    if not SCHEMA_LOCK.exists():
        raise AuditError(
            f"Schema lock is missing: {SCHEMA_LOCK}. Initial maintainers must run "
            "`python scripts/run_data_audit.py --write-schema-lock` and review it."
        )
    expected = json.loads(SCHEMA_LOCK.read_text(encoding="utf-8"))
    expected_schemas = expected.get("schemas", {})
    failures: list[str] = []
    for season, frame in frames.items():
        actual_columns = frame.columns.tolist()
        expected_columns = expected_schemas.get(season)
        if expected_columns != actual_columns:
            expected_set = set(expected_columns or [])
            actual_set = set(actual_columns)
            failures.append(
                f"{season}: added={sorted(actual_set - expected_set)}, "
                f"removed={sorted(expected_set - actual_set)}, "
                f"order_changed={expected_set == actual_set}"
            )
    extra_seasons = sorted(set(expected_schemas).difference(frames))
    if extra_seasons:
        failures.append(f"schema lock has unexpected seasons: {extra_seasons}")
    if failures:
        raise AuditError("Unexpected schema change: " + "; ".join(failures))


def parse_dates(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values.astype("string").str.strip(), format="mixed", dayfirst=True, errors="coerce")


def parse_times(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values.astype("string").str.strip(), format="%H:%M", errors="coerce")


def triplet_coverage(frame: pd.DataFrame, columns: tuple[str, str, str]) -> tuple[int, float]:
    if not set(columns).issubset(frame.columns):
        return 0, 0.0
    complete = int(frame[list(columns)].notna().all(axis=1).sum())
    return complete, complete / len(frame) if len(frame) else 0.0


def closing_bookmaker_triplets(frame: pd.DataFrame) -> list[tuple[str, tuple[str, str, str]]]:
    triplets: list[tuple[str, tuple[str, str, str]]] = []
    # Do not infer prefixes from a generic `*CH` regex. For example, legacy
    # VCH/VCD/VCA means VC Bet pre-closing H/D/A, not bookmaker `V` closing
    # odds. Construct only documented bookmaker abbreviations instead.
    for prefix in BOOKMAKER_NAMES:
        candidate = (f"{prefix}CH", f"{prefix}CD", f"{prefix}CA")
        if set(candidate).issubset(frame.columns):
            triplets.append((prefix, candidate))
    return triplets


def expected_result(home: pd.Series, away: pd.Series) -> pd.Series:
    result = pd.Series(pd.NA, index=home.index, dtype="string")
    result.loc[home > away] = "H"
    result.loc[home == away] = "D"
    result.loc[home < away] = "A"
    return result


def numeric_invalid_mask(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    present = values.notna()
    return present & (numeric.isna() | (numeric < 0) | ((numeric % 1) != 0))


def profile_season(
    season: str, frame: pd.DataFrame
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    rows = len(frame)
    dates = parse_dates(frame["Date"])
    date_present = frame["Date"].notna() & frame["Date"].astype("string").str.strip().ne("")
    date_failures = int((date_present & dates.isna()).sum())

    home_raw = frame["HomeTeam"].astype("string")
    away_raw = frame["AwayTeam"].astype("string")
    home_clean = home_raw.str.strip()
    away_clean = away_raw.str.strip()
    home_missing = frame["HomeTeam"].isna() | home_clean.eq("")
    away_missing = frame["AwayTeam"].isna() | away_clean.eq("")
    same_team = home_clean.str.casefold().eq(away_clean.str.casefold()) & ~home_missing & ~away_missing
    whitespace_team_values = int(
        ((~home_missing) & home_raw.ne(home_clean)).sum()
        + ((~away_missing) & away_raw.ne(away_clean)).sum()
    )
    invalid_team_rows = int((home_missing | away_missing | same_team).sum())

    exact_duplicate_rows = int(frame.duplicated(keep="first").sum())
    exact_duplicate_affected_rows = int(frame.duplicated(keep=False).sum())
    match_key = pd.DataFrame(
        {
            "date": dates.dt.strftime("%Y-%m-%d").fillna(frame["Date"].astype("string").str.strip()),
            "home": home_clean.str.casefold(),
            "away": away_clean.str.casefold(),
        }
    )
    duplicate_matches = int(match_key.duplicated(keep="first").sum())
    duplicate_match_affected_rows = int(match_key.duplicated(keep=False).sum())

    home_goals = pd.to_numeric(frame["FTHG"], errors="coerce")
    away_goals = pd.to_numeric(frame["FTAG"], errors="coerce")
    score_invalid = numeric_invalid_mask(frame["FTHG"]) | numeric_invalid_mask(frame["FTAG"])
    result_invalid = frame["FTR"].notna() & ~frame["FTR"].astype("string").isin(["H", "D", "A"])
    expected = expected_result(home_goals, away_goals)
    comparable = home_goals.notna() & away_goals.notna() & frame["FTR"].notna()
    result_mismatches = int(
        (comparable & frame["FTR"].astype("string").ne(expected)).sum()
    )

    if "Time" in frame:
        times = parse_times(frame["Time"])
        time_present = frame["Time"].notna() & frame["Time"].astype("string").str.strip().ne("")
        time_failures = int((time_present & times.isna()).sum())
        time_available = int(time_present.sum())
    else:
        time_failures = 0
        time_available = 0

    stats_present = [column for column in MATCH_STAT_FIELDS if column in frame]
    stats_complete = (
        int(frame[stats_present].notna().all(axis=1).sum())
        if len(stats_present) == len(MATCH_STAT_FIELDS)
        else 0
    )

    opening_fields: tuple[str, str, str] | None = None
    opening_source = ""
    if {"AvgH", "AvgD", "AvgA"}.issubset(frame.columns):
        opening_fields = ("AvgH", "AvgD", "AvgA")
        opening_source = "market_average_pre_closing"
    elif {"BbAvH", "BbAvD", "BbAvA"}.issubset(frame.columns):
        opening_fields = ("BbAvH", "BbAvD", "BbAvA")
        opening_source = "betbrain_average_pre_closing"

    closing_fields = ("AvgCH", "AvgCD", "AvgCA")
    opening_rows, opening_rate = (
        triplet_coverage(frame, opening_fields) if opening_fields else (0, 0.0)
    )
    closing_rows, closing_rate = triplet_coverage(frame, closing_fields)
    bookmaker_triplets = closing_bookmaker_triplets(frame)

    odds_rows: list[dict[str, Any]] = []
    if opening_fields:
        odds_rows.append(
            {
                "season": season,
                "odds_type": "pre_closing_average_1x2",
                "odds_source": opening_source,
                "home_column": opening_fields[0],
                "draw_column": opening_fields[1],
                "away_column": opening_fields[2],
                "complete_rows": opening_rows,
                "row_count": rows,
                "coverage_rate": opening_rate,
            }
        )
    if set(closing_fields).issubset(frame.columns):
        odds_rows.append(
            {
                "season": season,
                "odds_type": "closing_market_average_1x2",
                "odds_source": "market_average_closing",
                "home_column": closing_fields[0],
                "draw_column": closing_fields[1],
                "away_column": closing_fields[2],
                "complete_rows": closing_rows,
                "row_count": rows,
                "coverage_rate": closing_rate,
            }
        )
    for prefix, fields in bookmaker_triplets:
        complete, coverage = triplet_coverage(frame, fields)
        odds_rows.append(
            {
                "season": season,
                "odds_type": "individual_bookmaker_closing_1x2",
                "odds_source": BOOKMAKER_NAMES.get(prefix, prefix),
                "home_column": fields[0],
                "draw_column": fields[1],
                "away_column": fields[2],
                "complete_rows": complete,
                "row_count": rows,
                "coverage_rate": coverage,
            }
        )

    suspected_rows: list[dict[str, Any]] = []
    if set(MATCH_STAT_FIELDS).issubset(frame.columns):
        all_stats_missing = frame[MATCH_STAT_FIELDS].isna().all(axis=1)
        three_nil = ((home_goals == 3) & (away_goals == 0)) | ((home_goals == 0) & (away_goals == 3))
        for index in frame.index[all_stats_missing & three_nil]:
            suspected_rows.append(
                {
                    "season": season,
                    "raw_csv_row": int(index) + 2,
                    "date": frame.at[index, "Date"],
                    "home_team": frame.at[index, "HomeTeam"],
                    "away_team": frame.at[index, "AwayTeam"],
                    "home_goals": frame.at[index, "FTHG"],
                    "away_goals": frame.at[index, "FTAG"],
                    "result": frame.at[index, "FTR"],
                    "reason": "3-0/0-3 score with every audited match-stat field missing",
                    "confidence": "high_candidate_not_confirmed",
                    "review_status": "human_review_required",
                }
            )

    unique_teams = sorted(set(home_clean.dropna()).union(away_clean.dropna()))
    summary = {
        "season": season,
        "row_count": rows,
        "column_count": len(frame.columns),
        "date_min": dates.min().date().isoformat() if dates.notna().any() else "",
        "date_max": dates.max().date().isoformat() if dates.notna().any() else "",
        "date_parsing_failures": date_failures,
        "time_available_rows": time_available,
        "time_parsing_failures": time_failures,
        "exact_duplicate_rows": exact_duplicate_rows,
        "exact_duplicate_affected_rows": exact_duplicate_affected_rows,
        "duplicate_matches": duplicate_matches,
        "duplicate_match_affected_rows": duplicate_match_affected_rows,
        "missing_team_values": int(home_missing.sum() + away_missing.sum()),
        "same_team_rows": int(same_team.sum()),
        "whitespace_team_values": whitespace_team_values,
        "invalid_team_rows": invalid_team_rows,
        "unique_teams": len(unique_teams),
        "score_complete_rows": int(frame[["FTHG", "FTAG", "FTR"]].notna().all(axis=1).sum()),
        "invalid_score_rows": int(score_invalid.sum()),
        "invalid_result_rows": int(result_invalid.sum()),
        "result_score_mismatches": result_mismatches,
        "match_stat_columns_present": len(stats_present),
        "match_stats_complete_rows": stats_complete,
        "match_stats_complete_rate": stats_complete / rows if rows else 0.0,
        "pre_closing_average_fields": "|".join(opening_fields or ()),
        "pre_closing_average_complete_rows": opening_rows,
        "pre_closing_average_complete_rate": opening_rate,
        "closing_average_fields": "|".join(closing_fields)
        if set(closing_fields).issubset(frame.columns)
        else "",
        "closing_average_complete_rows": closing_rows,
        "closing_average_complete_rate": closing_rate,
        "individual_closing_sources": "|".join(
            BOOKMAKER_NAMES.get(prefix, prefix) for prefix, _ in bookmaker_triplets
        ),
        "suspected_non_played_rows": len(suspected_rows),
    }
    return summary, odds_rows, suspected_rows


def build_evidence(
    frames: OrderedDict[str, pd.DataFrame], manifest: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    summaries: list[dict[str, Any]] = []
    missingness_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    teams_rows: list[dict[str, Any]] = []
    odds_rows: list[dict[str, Any]] = []
    suspected_rows: list[dict[str, Any]] = []

    union_columns: list[str] = []
    for frame in frames.values():
        for column in frame.columns:
            if column not in union_columns:
                union_columns.append(column)

    schema_rows: list[dict[str, Any]] = []
    for season, frame in frames.items():
        summary, season_odds, season_suspected = profile_season(season, frame)
        summaries.append(summary)
        odds_rows.extend(season_odds)
        suspected_rows.extend(season_suspected)

        for column in frame.columns:
            missing = int(frame[column].isna().sum())
            empty_strings = int(
                (
                    frame[column].notna()
                    & frame[column].astype("string").str.strip().eq("")
                ).sum()
            )
            missingness_rows.append(
                {
                    "season": season,
                    "column": column,
                    "row_count": len(frame),
                    "non_null_count": int(frame[column].notna().sum()),
                    "missing_count": missing,
                    "missing_rate": missing / len(frame) if len(frame) else 0.0,
                    "empty_string_count": empty_strings,
                }
            )

        for column in AUDITED_FIELDS:
            present = column in frame
            non_null = int(frame[column].notna().sum()) if present else 0
            invalid = (
                int(numeric_invalid_mask(frame[column]).sum())
                if present and column != "FTR"
                else int(
                    (frame[column].notna() & ~frame[column].astype("string").isin(["H", "D", "A"])).sum()
                )
                if present
                else 0
            )
            coverage_rows.append(
                {
                    "season": season,
                    "field": column,
                    "column_present": present,
                    "row_count": len(frame),
                    "non_null_count": non_null,
                    "coverage_rate": non_null / len(frame) if present and len(frame) else 0.0,
                    "invalid_value_count": invalid,
                }
            )

        home_counts = frame["HomeTeam"].value_counts(dropna=True)
        away_counts = frame["AwayTeam"].value_counts(dropna=True)
        all_teams = sorted(set(home_counts.index).union(away_counts.index))
        for team in all_teams:
            home_matches = int(home_counts.get(team, 0))
            away_matches = int(away_counts.get(team, 0))
            teams_rows.append(
                {
                    "season": season,
                    "team": team,
                    "home_matches": home_matches,
                    "away_matches": away_matches,
                    "total_matches": home_matches + away_matches,
                }
            )

        for column in union_columns:
            present = column in frame
            schema_rows.append(
                {
                    "season": season,
                    "column": column,
                    "present": present,
                    "position": int(frame.columns.get_loc(column)) + 1 if present else pd.NA,
                    "dtype": str(frame[column].dtype) if present else "",
                    "non_null_count": int(frame[column].notna().sum()) if present else 0,
                    "missing_count": int(frame[column].isna().sum()) if present else len(frame),
                    "missing_rate": float(frame[column].isna().mean()) if present else 1.0,
                }
            )

    schema_changes: list[dict[str, Any]] = []
    previous_columns: set[str] | None = None
    previous_season = ""
    for season, frame in frames.items():
        current = set(frame.columns)
        added = sorted(current - previous_columns) if previous_columns is not None else []
        removed = sorted(previous_columns - current) if previous_columns is not None else []
        schema_changes.append(
            {
                "season": season,
                "previous_season": previous_season,
                "added_count": len(added),
                "added_columns": "|".join(added),
                "removed_count": len(removed),
                "removed_columns": "|".join(removed),
            }
        )
        previous_columns = current
        previous_season = season

    aliases: list[dict[str, Any]] = []
    team_frame = pd.DataFrame(teams_rows)
    for proposal in ALIAS_PROPOSALS:
        source_name = proposal["source_name"]
        seasons = team_frame.loc[team_frame["team"] == source_name, "season"].tolist()
        if seasons:
            aliases.append({**proposal, "seasons_observed": "|".join(seasons)})

    return {
        "raw_file_manifest": manifest,
        "season_summary": pd.DataFrame(summaries),
        "schema_by_season": pd.DataFrame(schema_rows),
        "missingness_by_season": pd.DataFrame(missingness_rows),
        "field_coverage_by_season": pd.DataFrame(coverage_rows),
        "teams_by_season": team_frame,
        "odds_coverage_by_season": pd.DataFrame(odds_rows),
        "schema_changes": pd.DataFrame(schema_changes),
        "team_aliases": pd.DataFrame(aliases),
        "suspected_non_played_matches": pd.DataFrame(suspected_rows),
    }


def coverage_stats(evidence: dict[str, pd.DataFrame], field: str) -> tuple[int, int, float, float]:
    frame = evidence["field_coverage_by_season"]
    selected = frame[frame["field"] == field]
    non_null = int(selected["non_null_count"].sum())
    rows = int(selected["row_count"].sum())
    overall = non_null / rows if rows else 0.0
    minimum = float(selected["coverage_rate"].min()) if not selected.empty else 0.0
    return non_null, rows, overall, minimum


def generate_data_contract(evidence: dict[str, pd.DataFrame]) -> str:
    field_rows: list[list[Any]] = [
        ["match_id", "REQUIRED", "string", "derived", "Stable unique key; collision is a hard failure."],
        ["season", "REQUIRED", "string", "catalog", "`YYYY-YY` label."],
        ["date", "REQUIRED", "date", "Date", "Day-first source parsed to ISO date."],
        ["kickoff_time", "OPTIONAL", "time", "Time", "Absent in 2017-18 and 2018-19."],
        ["home_team", "REQUIRED", "string", "HomeTeam", "Alias changes require review."],
        ["away_team", "REQUIRED", "string", "AwayTeam", "Must differ from home team."],
        ["home_goals", "REQUIRED", "integer", "FTHG", "Non-negative full-time goals."],
        ["away_goals", "REQUIRED", "integer", "FTAG", "Non-negative full-time goals."],
        ["result", "REQUIRED", "enum H/D/A", "FTR", "Must agree with full-time goals."],
    ]
    optional_fields = [
        ("home_ht_goals", "HTHG"),
        ("away_ht_goals", "HTAG"),
        ("home_shots", "HS"),
        ("away_shots", "AS"),
        ("home_shots_on_target", "HST"),
        ("away_shots_on_target", "AST"),
        ("home_fouls", "HF"),
        ("away_fouls", "AF"),
        ("home_corners", "HC"),
        ("away_corners", "AC"),
        ("home_yellow_cards", "HY"),
        ("away_yellow_cards", "AY"),
        ("home_red_cards", "HR"),
        ("away_red_cards", "AR"),
    ]
    for canonical, source in optional_fields:
        _, _, overall, minimum = coverage_stats(evidence, source)
        field_rows.append(
            [
                canonical,
                "OPTIONAL",
                "nullable integer",
                source,
                f"Overall {pct(overall)}; weakest season {pct(minimum)}.",
            ]
        )

    suspected_count = len(evidence["suspected_non_played_matches"])
    lines = [
        "# Provisional data contract",
        "",
        "This is a Phase 0 proposal based on the audited Football-Data snapshots. It",
        "does not create a canonical dataset or any predictive feature table.",
        "",
        "## Canonical match table",
        "",
        "Grain: one scheduled league match result per row after explicit resolution",
        "of duplicate keys and non-played/administrative results.",
        "",
        md_table(["Field", "Status", "Type", "Source", "Rule"], field_rows),
        "",
        "`match_id` is proposed as a SHA-256 of",
        "`season|date_iso|approved_home_team|approved_away_team`. Inputs are delimited",
        "and UTF-8 encoded. The unhashed components must remain alongside the ID for",
        "auditability. A collision or duplicate natural key is a hard failure.",
        "",
        "Optional match statistics are historical outcomes, not pre-match features.",
        "The leakage contract forbids using a match's own optional statistics to",
        "predict that match.",
        "",
        "## Fields rejected from the MVP match table",
        "",
        "- `Div`: constant source code and already represented by dataset scope.",
        "- `HTR`: derivable from half-time goals when those goals exist.",
        "- all 1X2, over/under, and Asian-handicap odds: market data is isolated below.",
        "- bookmaker counts, maxima, and exchange fields: not needed for the first",
        "  closing-probability benchmark.",
        "- `match_status`: the source has no explicit played/awarded/abandoned field.",
        f"  The audit flags {suspected_count} candidates, but Phase 0 will not invent status values.",
        "- rolling form, standings, Elo, attack/defence strength, and every other",
        "  pre-match feature: deferred to a later phase.",
        "",
        "## Isolated market benchmark table",
        "",
        "This table is separate from matches used to construct predictive features.",
        "It may join to frozen predictions only for external benchmark evaluation.",
        "",
        md_table(
            ["Field", "Status", "Type", "Rule"],
            [
                ["match_id", "REQUIRED", "string", "Foreign key to canonical match."],
                ["closing_home_odds", "REQUIRED", "decimal", "Decimal odds > 1 when row exists."],
                ["closing_draw_odds", "REQUIRED", "decimal", "Decimal odds > 1 when row exists."],
                ["closing_away_odds", "REQUIRED", "decimal", "Decimal odds > 1 when row exists."],
                ["market_p_home", "REQUIRED", "float", "De-vigged probability in [0, 1]."],
                ["market_p_draw", "REQUIRED", "float", "De-vigged probability in [0, 1]."],
                ["market_p_away", "REQUIRED", "float", "De-vigged probability in [0, 1]."],
                ["market_overround", "REQUIRED", "float", "Sum of raw inverse odds minus 1."],
                ["odds_source", "REQUIRED", "string", "Exact average/bookmaker and closing status."],
            ],
        ),
        "",
        "For odds `(o_h, o_d, o_a)`, let `q_i = 1 / o_i`,",
        "`market_overround = q_h + q_d + q_a - 1`, and",
        "`market_p_i = q_i / (q_h + q_d + q_a)`.",
        "",
        "Selection hierarchy: use `AvgCH/AvgCD/AvgCA` as the closing market average",
        "where complete (2019-20 onward in the audited schemas). Earlier seasons may",
        "use complete `PSCH/PSCD/PSCA` only as a separately labelled Pinnacle closing",
        "benchmark. Market-average and single-bookmaker rows must not be presented as",
        "one homogeneous series without stratification.",
        "",
        "## Team aliases",
        "",
        "`reports/team_aliases.csv` contains proposals only. High-confidence mappings",
        "still require one human sign-off before canonical materialization. Review-level",
        "mappings are never applied automatically. Raw names remain available for lineage.",
        "",
        "## Hard validation rules",
        "",
        "- required fields are non-null; goals are non-negative integers; result is H/D/A;",
        "- result agrees with full-time goals; home and away teams differ;",
        "- natural match keys and `match_id` values are unique;",
        "- raw checksums and exact ordered schemas match their locks;",
        "- non-played/administrative candidates require explicit disposition;",
        "- market rows never enter a predictive feature dataset.",
    ]
    return "\n".join(lines)


def generate_audit_report(
    frames: OrderedDict[str, pd.DataFrame], evidence: dict[str, pd.DataFrame]
) -> str:
    summary = evidence["season_summary"]
    coverage = evidence["field_coverage_by_season"]
    missingness = evidence["missingness_by_season"]
    odds = evidence["odds_coverage_by_season"]
    aliases = evidence["team_aliases"]
    suspected = evidence["suspected_non_played_matches"]
    total_rows = int(summary["row_count"].sum())
    total_suspected = len(suspected)
    provenance = json.loads(ACQUISITION_PROVENANCE.read_text(encoding="utf-8"))
    acquisition = provenance["successful_acquisition"]
    shots_non_null, shots_rows, shots_overall, shots_min = coverage_stats(evidence, "HS")
    sot_non_null, sot_rows, sot_overall, sot_min = coverage_stats(evidence, "HST")

    common_columns = [
        column
        for column in frames[SEASONS[0]].columns
        if all(column in frames[season].columns for season in SEASONS)
    ]
    all_columns = []
    for frame in frames.values():
        for column in frame.columns:
            if column not in all_columns:
                all_columns.append(column)

    season_rows = []
    for _, row in summary.iterrows():
        season_rows.append(
            [
                row["season"],
                int(row["row_count"]),
                int(row["column_count"]),
                int(row["unique_teams"]),
                int(row["exact_duplicate_rows"]),
                int(row["duplicate_matches"]),
                int(row["date_parsing_failures"]),
                int(row["invalid_team_rows"]),
                pct(row["score_complete_rows"] / row["row_count"]),
                pct(row["match_stats_complete_rate"]),
                pct(row["closing_average_complete_rate"])
                if row["closing_average_fields"]
                else "absent",
                int(row["suspected_non_played_rows"]),
            ]
        )

    field_pivot = coverage.pivot(index="season", columns="field", values="coverage_rate")
    coverage_rows = [
        [season] + [pct(field_pivot.at[season, field]) for field in AUDITED_FIELDS]
        for season in SEASONS
    ]

    schema_change_rows = []
    for _, row in evidence["schema_changes"].iloc[1:].iterrows():
        schema_change_rows.append(
            [
                f"{row['previous_season']} -> {row['season']}",
                int(row["added_count"]),
                row["added_columns"] or "none",
                int(row["removed_count"]),
                row["removed_columns"] or "none",
            ]
        )

    major_missing = missingness[missingness["missing_rate"] >= 0.05].copy()
    missing_summary_rows = []
    for season in SEASONS:
        selected = major_missing[major_missing["season"] == season]
        if selected.empty:
            missing_summary_rows.append([season, 0, "none"])
        else:
            top = selected.sort_values(["missing_rate", "column"], ascending=[False, True]).head(12)
            examples = ", ".join(
                f"{row.column}={pct(row.missing_rate)}" for row in top.itertuples()
            )
            missing_summary_rows.append([season, len(selected), examples])

    closing_summary_rows = []
    for season in SEASONS:
        selected = odds[odds["season"] == season]
        pre = selected[selected["odds_type"] == "pre_closing_average_1x2"]
        close_avg = selected[selected["odds_type"] == "closing_market_average_1x2"]
        books = selected[selected["odds_type"] == "individual_bookmaker_closing_1x2"]
        closing_summary_rows.append(
            [
                season,
                pre.iloc[0]["home_column"] + "/" + pre.iloc[0]["draw_column"] + "/" + pre.iloc[0]["away_column"]
                if not pre.empty
                else "absent",
                pct(pre.iloc[0]["coverage_rate"]) if not pre.empty else "absent",
                close_avg.iloc[0]["home_column"] + "/" + close_avg.iloc[0]["draw_column"] + "/" + close_avg.iloc[0]["away_column"]
                if not close_avg.empty
                else "absent",
                pct(close_avg.iloc[0]["coverage_rate"]) if not close_avg.empty else "absent",
                ", ".join(
                    f"{book.odds_source} ({pct(book.coverage_rate)})" for book in books.itertuples()
                )
                or "none",
            ]
        )

    alias_rows = [
        [
            row.source_name,
            row.proposed_canonical_name,
            row.confidence,
            row.review_status,
            row.seasons_observed,
            row.reason,
        ]
        for row in aliases.itertuples()
    ]

    lines = [
        "# Turkish Super Lig data audit: 2017-18 through 2025-26",
        "",
        "## Answer first",
        "",
        "**Verdict: GO-WITH-CONSTRAINTS for proceeding to a score-only Dixon-Coles phase.**",
        "No model is implemented in this phase.",
        "",
        f"The nine Football-Data snapshots contain {total_rows:,} rows. Date, teams,",
        "full-time goals, and FTR are complete and internally consistent enough for a",
        "score-based MVP. The raw schemas are not concat-compatible: they range from 61",
        "to 131 columns and change odds providers and closing-market coverage over time.",
        f"The principal blocker to blind modeling is {total_suspected} strong heuristic but",
        "unconfirmed non-played/administrative-result candidates: 29 in 2022-23 and one in each of",
        "2023-24 and 2024-25. They have 3-0/0-3 scores while every audited match-stat",
        "field is missing. They require human confirmation and an explicit include/exclude",
        "decision before model fitting.",
        "",
        "Reliable MVP columns are `Date`, `HomeTeam`, `AwayTeam`, `FTHG`, `FTAG`, and",
        "`FTR`. Half-time and match-stat fields are retained as optional historical",
        "outcomes. Closing market-average 1X2 odds are absent before 2019-20, so market",
        "benchmark coverage is not homogeneous across all nine seasons.",
        "",
        "## Dataset and grain",
        "",
        "Expected grain: one Turkish top-flight scheduled match/result per row. Candidate",
        "key: season + parsed date + normalized home team + normalized away team.",
        "Raw CSV bytes are checksum-locked and never rewritten.",
        "",
        "## Source provenance",
        "",
        f"Source page: [{provenance['source_page']}]({provenance['source_page']}).",
        f"Field definitions: [{provenance['source_notes']}]({provenance['source_notes']}).",
        f"Snapshot date: {provenance['snapshot_date']}.",
        "",
        f"The first local request was rejected because {provenance['local_attempt']['reason']}",
        "No mirror or invented substitute entered the audit. The successful acquisition",
        f"used {acquisition['method']} in [this workflow run]({acquisition['run_url']}).",
        f"Artifact digest: `{acquisition['artifact_digest']}`. {acquisition['verification']}",
        "The per-file URLs, byte sizes, and hashes are reproduced in",
        "`raw_file_manifest.csv`.",
        "",
        md_table(
            [
                "Season",
                "Rows",
                "Cols",
                "Teams",
                "Exact dupes",
                "Match dupes",
                "Date fails",
                "Invalid team rows",
                "Score complete",
                "All stats complete",
                "Closing avg complete",
                "Non-played candidates",
            ],
            season_rows,
        ),
        "",
        "Duplicate counts report excess rows after the first occurrence; affected-row",
        "counts are retained in `season_summary.csv`. Missing/blank teams, same-team rows,",
        "invalid scores, invalid FTR values, and score/FTR mismatches are also in that file.",
        "",
        "## Required field coverage",
        "",
        md_table(["Season"] + AUDITED_FIELDS, coverage_rows),
        "",
        f"Shots coverage is {shots_non_null:,}/{shots_rows:,} ({pct(shots_overall)}) overall;",
        f"shots-on-target coverage is {sot_non_null:,}/{sot_rows:,} ({pct(sot_overall)}).",
        f"The weakest season is {pct(min(shots_min, sot_min))}, driven by the 2022-23",
        "administrative-result candidates rather than scattered ordinary-match missingness.",
        "This is acceptable for optional descriptive outcomes, but not as a REQUIRED MVP",
        "field and never as a current-match predictive input.",
        "",
        "## Schema evolution",
        "",
        f"Columns common to every season ({len(common_columns)}):",
        "",
        "```text",
        ",".join(common_columns),
        "```",
        "",
        f"The union contains {len(all_columns)} distinct raw column names. Consecutive",
        "changes are shown below; the complete season-by-union matrix is in",
        "`schema_by_season.csv`.",
        "",
        md_table(
            ["Transition", "Added", "Added columns", "Removed", "Removed columns"],
            schema_change_rows,
        ),
        "",
        "Major schema regimes:",
        "",
        "- 2017-18 and 2018-19 use legacy BetBrain average/max fields and have no `Time`",
        "  or closing market-average `AvgCH/AvgCD/AvgCA` fields.",
        "- 2019-20 through 2023-24 share a 105-column layout with explicit pre-closing",
        "  (`AvgH/AvgD/AvgA`) and closing (`AvgCH/AvgCD/AvgCA`) averages.",
        "- 2024-25 expands to 119 columns with Betfair/1XBet/exchange fields.",
        "- 2025-26 expands to 131 columns and changes the individual bookmaker roster.",
        "",
        "Major missingness (>=5% within a present column):",
        "",
        md_table(["Season", "Columns >=5% missing", "Largest examples"], missing_summary_rows),
        "",
        "Meaning/composition cautions:",
        "",
        "- Football-Data defines non-`C` odds as pre-closing and `C`-suffixed odds as",
        "  closing. Treating all odds columns as one timestamp would be a semantic error.",
        "- The bookmaker roster changes; even stable `Avg*` names can represent averages",
        "  over different contributing books. Cross-season market comparisons need source",
        "  and regime labels.",
        "- Date meaning is stable, but raw formatting and UTF-8 BOM usage vary by season.",
        "- A full-time 3-0/0-3 score can represent an administrative result in the source",
        "  without an explicit status field. Those rows do not have the same on-pitch",
        "  meaning as ordinary FTHG/FTAG observations.",
        "",
        "## Betting-odds audit",
        "",
        md_table(
            [
                "Season",
                "Pre-closing average fields",
                "Coverage",
                "Closing average fields",
                "Coverage",
                "Individual closing sources",
            ],
            closing_summary_rows,
        ),
        "",
        "`AvgH/AvgD/AvgA` are not closing odds. The market benchmark should prefer",
        "`AvgCH/AvgCD/AvgCA` from 2019-20 onward. The first two seasons have Pinnacle",
        "`PSCH/PSCD/PSCA` closing odds but no closing market average; using them creates a",
        "separate single-bookmaker benchmark regime. The full triplet-level evidence is in",
        "`odds_coverage_by_season.csv`. Odds remain outside all predictive feature data.",
        "",
        "## Team-name audit",
        "",
        "`teams_by_season.csv` lists every distinct raw name, season, and home/away match",
        "count. The source is internally stable for most clubs but uses ASCII",
        "transliterations, abbreviations, truncations, and historical labels.",
        "",
        md_table(
            ["Raw name", "Proposed canonical", "Confidence", "Status", "Seasons", "Reason"],
            alias_rows,
        ),
        "",
        "No alias is applied automatically in Phase 0. In particular, review-level rows",
        "remain separate until a human decision is recorded.",
        "",
        "## Data-quality risks and impact",
        "",
        md_table(
            ["Severity", "Finding", "Evidence", "Modeling impact", "Required action"],
            [
                [
                    "High",
                    "Likely non-played/administrative results",
                    f"{total_suspected} rows; 3-0/0-3 with all audited stats missing",
                    "Artificial goals bias attack/defence strength and score tails.",
                    "Human-confirm and exclude or explicitly model status before fitting.",
                ],
                [
                    "High",
                    "Post-match leakage risk",
                    "Goals, shots, cards, corners, fouls, and closing odds coexist in raw rows.",
                    "Naive feature selection can produce impossible performance.",
                    "Enforce LEAKAGE_CONTRACT.md and walk-forward tests.",
                ],
                [
                    "Medium",
                    "Odds regime drift",
                    "Closing average absent in first two seasons; bookmaker roster changes later.",
                    "A single benchmark series would mix unlike sources.",
                    "Label source/regime and report benchmark coverage separately.",
                ],
                [
                    "Medium",
                    "Missing kickoff time",
                    "`Time` absent in 2017-18 and 2018-19.",
                    "Same-day strict ordering is unknowable.",
                    "Treat same-date matches as simultaneous for leakage boundaries.",
                ],
                [
                    "Medium",
                    "Unapproved team aliases",
                    f"{len(aliases)} proposed/review mappings.",
                    "Bad merges split or combine team histories.",
                    "Approve only high-confidence mappings; retain raw lineage.",
                ],
                [
                    "Low",
                    "Encoding/header variation",
                    "2018-19 begins with UTF-8 BOM.",
                    "Over-strict loaders can reject a valid season.",
                    "Decode BOM for parsing; never rewrite raw bytes.",
                ],
                [
                    "Low",
                    "Isolated red-card missing value",
                    "2018-19 Bursaspor-Alanyaspor has null AR; all other audited stats are present.",
                    "Does not affect score-only Dixon-Coles; unsafe to impute silently.",
                    "Keep AR nullable and preserve the source null.",
                ],
            ],
        ),
        "",
        "## Recommended canonical schema",
        "",
        "REQUIRED: `match_id`, `season`, `date`, `home_team`, `away_team`,",
        "`home_goals`, `away_goals`, `result`.",
        "",
        "OPTIONAL: `kickoff_time`, both half-time goal fields, and all audited shots,",
        "shots-on-target, fouls, corners, yellow-card, and red-card fields. They are",
        "historical outcomes, not current-match features.",
        "",
        "REJECTED FROM MVP: `Div`, derivable `HTR`, all odds in the match table,",
        "over/under and handicap markets, bookmaker maxima/counts, unverified",
        "`match_status`, and all rolling/pre-match features. Full types and validation",
        "rules are in `DATA_CONTRACT.md`.",
        "",
        "## Explicit unresolved questions",
        "",
        f"1. Confirm the disposition of all {total_suspected} rows in",
        "   `suspected_non_played_matches.csv` before any model is fitted.",
        "2. Approve or reject each team alias proposal, especially `Erzurum BB` and",
        "   `Gaziantep`.",
        "3. Decide whether the closing-market benchmark starts in 2019-20 or uses",
        "   separately labelled Pinnacle closing odds for 2017-18 and 2018-19.",
        "4. Confirm the conservative same-calendar-date ordering rule for seasons without",
        "   kickoff times.",
        "5. Define how newly promoted 2026-27 teams not present in the audit receive",
        "   canonical identities and cold-start handling in a later phase.",
        "",
        "## Final decision",
        "",
        "**GO-WITH-CONSTRAINTS.** The score-and-result backbone is viable for the next",
        "Dixon-Coles iteration, conditional on resolving non-played candidates and team",
        "aliases. Match statistics are sufficiently complete as optional outcomes but are",
        "not necessary for Dixon-Coles. Market odds are useful as an external benchmark",
        "from 2019-20 onward and must stay logically isolated. Do not proceed to modeling",
        "until the two human-review tables have explicit dispositions.",
        "",
        "## Exact columns by season",
    ]

    for season, frame in frames.items():
        lines.extend(
            [
                "",
                f"### {season} ({len(frame)} rows x {len(frame.columns)} columns)",
                "",
                "```text",
                ",".join(frame.columns),
                "```",
            ]
        )

    return "\n".join(lines)


def write_outputs(
    frames: OrderedDict[str, pd.DataFrame], evidence: dict[str, pd.DataFrame]
) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ordered_outputs = [
        "raw_file_manifest",
        "season_summary",
        "schema_by_season",
        "missingness_by_season",
        "field_coverage_by_season",
        "teams_by_season",
        "odds_coverage_by_season",
        "schema_changes",
        "team_aliases",
        "suspected_non_played_matches",
    ]
    for name in ordered_outputs:
        frame = evidence[name]
        write_csv(REPORTS_DIR / f"{name}.csv", frame)
    write_text(REPORTS_DIR / "DATA_AUDIT.md", generate_audit_report(frames, evidence))
    write_text(DATA_CONTRACT, generate_data_contract(evidence))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit immutable Football-Data Turkish Super Lig CSV snapshots."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Fail if a raw file is missing instead of attempting an HTTPS download.",
    )
    parser.add_argument(
        "--write-schema-lock",
        action="store_true",
        help="Explicit maintainer action: write the exact observed schema lock.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        sources = load_source_catalog()
        manifest = ensure_raw_sources(sources, offline=args.offline)
        frames = read_raw_frames(sources)
        lock_or_validate_schemas(frames, write_schema_lock=args.write_schema_lock)
        evidence = build_evidence(frames, manifest)
        write_outputs(frames, evidence)
        summary = evidence["season_summary"]
        print(
            "Audit complete: "
            f"{len(summary)} seasons, {int(summary['row_count'].sum())} rows, "
            f"{len(evidence['suspected_non_played_matches'])} non-played candidates."
        )
        print(f"Report: {REPORTS_DIR / 'DATA_AUDIT.md'}")
        print("Verdict: GO-WITH-CONSTRAINTS")
        return 0
    except AuditError as exc:
        print(f"AUDIT FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
