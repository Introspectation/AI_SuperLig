#!/usr/bin/env python3
"""Build deterministic canonical match and isolated market benchmark tables."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

import run_data_audit as audit


ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"
CANONICAL_MATCHES = PROCESSED_DIR / "canonical_matches.csv"
MARKET_BENCHMARK = PROCESSED_DIR / "market_benchmark.csv"
TFF_SNAPSHOT = ROOT / "data" / "raw" / "tff" / "kickoff_times_2017-19.csv"
TFF_MANIFEST = ROOT / "data" / "raw" / "tff" / "kickoff_times_2017-19.manifest.json"
TFF_TEAM_ALIASES = ROOT / "config" / "tff_team_aliases.csv"
KICKOFF_DATE_DISCREPANCIES = ROOT / "config" / "kickoff_date_discrepancies.csv"
KICKOFF_SCORE_DISCREPANCIES = ROOT / "config" / "kickoff_score_discrepancies.csv"
KICKOFF_REVIEW_SOURCES = ROOT / "config" / "kickoff_review_sources.csv"
QUALITY_REPORT = ROOT / "reports" / "CANONICAL_DATA_AUDIT.md"
QUALITY_BY_SEASON = ROOT / "reports" / "canonical_data_quality_by_season.csv"
TFF_JOIN_AUDIT = ROOT / "reports" / "tff_kickoff_join_audit.csv"

EARLY_KICKOFF_SEASONS = {"2017-18", "2018-19"}
FOOTBALL_DATA_TIMEZONE = ZoneInfo("Europe/London")
CANONICAL_TIMEZONE = ZoneInfo("Europe/Istanbul")
TIMEZONE_EVIDENCE_IDS = {"TFF_2019_WEEK1", "TFF_2020_WEEK18"}
OPTIONAL_FIELD_MAP = OrderedDict(
    [
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
CANONICAL_COLUMNS = [
    "match_id",
    "season",
    "date",
    "kickoff_time",
    "kickoff_timezone",
    "kickoff_time_source",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "result",
    "official_home_goals",
    "official_away_goals",
    "official_result",
    "match_status",
    "model_eligible",
    *OPTIONAL_FIELD_MAP.keys(),
    "source_provider",
    "source_file",
    "source_row",
    "tff_match_id",
]
MARKET_COLUMNS = [
    "match_id",
    "season",
    "benchmark_tier",
    "benchmark_regime",
    "closing_home_odds",
    "closing_draw_odds",
    "closing_away_odds",
    "market_p_home",
    "market_p_draw",
    "market_p_away",
    "market_overround",
    "odds_source",
]


class CanonicalBuildError(RuntimeError):
    """A deterministic build or data-contract failure."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_match_id(season: str, date: str, home_team: str, away_team: str) -> str:
    value = "|".join([season, date, home_team, away_team]).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def convert_football_data_kickoff(date_iso: str, kickoff_time: str) -> tuple[str, str]:
    """Convert Football-Data's UK clock time to the canonical Turkish timezone."""
    source_datetime = datetime.strptime(
        f"{date_iso} {kickoff_time}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=FOOTBALL_DATA_TIMEZONE)
    canonical_datetime = source_datetime.astimezone(CANONICAL_TIMEZONE)
    return canonical_datetime.date().isoformat(), canonical_datetime.strftime("%H:%M")


def load_alias_map(path: Path, decision: str) -> dict[str, str]:
    if not path.exists():
        raise CanonicalBuildError(f"Missing reviewed alias config: {path}")
    frame = pd.read_csv(path, dtype="string")
    required = {"source_name", "canonical_name", "confidence", "decision"}
    missing = required.difference(frame.columns)
    if missing:
        raise CanonicalBuildError(f"Alias config {path.name} missing: {sorted(missing)}")
    if frame[list(required)].isna().any(axis=None):
        raise CanonicalBuildError(f"Alias config {path.name} contains null required values")
    if frame["source_name"].duplicated().any():
        raise CanonicalBuildError(f"Alias config {path.name} contains duplicate source names")
    if set(frame["confidence"]) != {"high"} or set(frame["decision"]) != {decision}:
        raise CanonicalBuildError(
            f"Alias config {path.name} contains unapproved or non-high-confidence rows"
        )
    return dict(zip(frame["source_name"], frame["canonical_name"], strict=True))


def validate_tff_snapshot() -> tuple[pd.DataFrame, dict[str, str]]:
    if not TFF_SNAPSHOT.exists() or not TFF_MANIFEST.exists():
        raise CanonicalBuildError(
            "Missing immutable TFF kickoff snapshot. Run "
            "`python scripts/bootstrap_tff_kickoffs.py` once and review the result."
        )
    manifest = json.loads(TFF_MANIFEST.read_text(encoding="utf-8"))
    if sha256_file(TFF_SNAPSHOT) != manifest.get("snapshot_sha256"):
        raise CanonicalBuildError("Immutable TFF kickoff snapshot checksum mismatch")
    if TFF_SNAPSHOT.stat().st_size != int(manifest.get("snapshot_bytes", -1)):
        raise CanonicalBuildError("Immutable TFF kickoff snapshot byte-size mismatch")
    if int(manifest.get("row_count", -1)) != 612:
        raise CanonicalBuildError("TFF kickoff manifest row count changed")
    source_pages = manifest.get("source_pages", [])
    if len(source_pages) != 68 or any(int(page.get("match_rows", -1)) != 9 for page in source_pages):
        raise CanonicalBuildError("TFF source-page manifest no longer represents 68 complete weeks")

    frame = pd.read_csv(
        TFF_SNAPSHOT,
        dtype={"season": "string", "tff_match_id": "string"},
    )
    expected_columns = [
        "season",
        "week",
        "date",
        "kickoff_time",
        "home_team_tff",
        "away_team_tff",
        "home_goals",
        "away_goals",
        "tff_match_id",
        "source_url",
    ]
    if frame.columns.tolist() != expected_columns:
        raise CanonicalBuildError("Unexpected TFF kickoff snapshot schema")
    if len(frame) != 612 or frame["tff_match_id"].duplicated().any():
        raise CanonicalBuildError("TFF kickoff snapshot grain changed")

    alias_map = load_alias_map(TFF_TEAM_ALIASES, "approved_for_kickoff_join")
    observed = set(frame["home_team_tff"]).union(frame["away_team_tff"])
    configured = set(alias_map)
    if observed != configured:
        raise CanonicalBuildError(
            "TFF team alias coverage changed. "
            f"Unmapped={sorted(observed - configured)}; unused={sorted(configured - observed)}"
        )

    mapped = frame.copy()
    mapped["home_team"] = mapped["home_team_tff"].map(alias_map)
    mapped["away_team"] = mapped["away_team_tff"].map(alias_map)
    join_key = ["season", "date", "home_team", "away_team"]
    if mapped[join_key].isna().any(axis=None) or mapped.duplicated(join_key).any():
        raise CanonicalBuildError("TFF canonical kickoff keys are null or duplicated")
    return mapped, alias_map


def build_base_matches(
    frames: OrderedDict[str, pd.DataFrame],
) -> pd.DataFrame:
    football_aliases = load_alias_map(
        audit.TEAM_ALIAS_DECISIONS, "approved_for_canonicalization"
    )
    overrides = pd.read_csv(audit.MATCH_STATUS_OVERRIDES, dtype="string")
    overrides = overrides.copy()
    overrides["date_iso"] = audit.parse_dates(overrides["date"]).dt.strftime("%Y-%m-%d")
    if overrides["date_iso"].isna().any():
        raise CanonicalBuildError("Match-status overrides contain an invalid date")
    override_key = ["season", "date_iso", "home_team_raw", "away_team_raw"]
    overrides = overrides.rename(
        columns={
            "home_team": "home_team_raw",
            "away_team": "away_team_raw",
        }
    )
    if overrides.duplicated(override_key).any():
        raise CanonicalBuildError("Match-status override keys are duplicated")

    pieces: list[pd.DataFrame] = []
    for season, raw in frames.items():
        dates = audit.parse_dates(raw["Date"])
        if dates.isna().any():
            raise CanonicalBuildError(f"{season}: canonical build found invalid dates")
        piece = pd.DataFrame(
            {
                "season": season,
                "date": dates.dt.strftime("%Y-%m-%d"),
                "home_team_raw": raw["HomeTeam"].astype("string").str.strip(),
                "away_team_raw": raw["AwayTeam"].astype("string").str.strip(),
                "home_goals": pd.to_numeric(raw["FTHG"], errors="raise").astype("int64"),
                "away_goals": pd.to_numeric(raw["FTAG"], errors="raise").astype("int64"),
                "result": raw["FTR"].astype("string"),
                "source_provider": "football_data",
                "source_file": f"data/raw/football_data/{season}.csv",
                "source_row": raw.index.to_series().astype("int64") + 2,
            }
        )
        piece["home_team"] = piece["home_team_raw"].replace(football_aliases)
        piece["away_team"] = piece["away_team_raw"].replace(football_aliases)
        if "Time" in raw:
            parsed_times = audit.parse_times(raw["Time"])
            present = raw["Time"].notna() & raw["Time"].astype("string").str.strip().ne("")
            if (present & parsed_times.isna()).any():
                raise CanonicalBuildError(f"{season}: invalid Football-Data kickoff time")
            source_times = parsed_times.dt.strftime("%H:%M")
            if source_times.isna().any():
                raise CanonicalBuildError(f"{season}: missing Football-Data kickoff time")
            converted = [
                convert_football_data_kickoff(date, kickoff)
                for date, kickoff in zip(piece["date"], source_times, strict=True)
            ]
            converted_dates = [date for date, _ in converted]
            if converted_dates != piece["date"].tolist():
                raise CanonicalBuildError(
                    f"{season}: timezone conversion changed a match date; review required"
                )
            piece["kickoff_time"] = pd.Series(
                [kickoff for _, kickoff in converted], index=piece.index, dtype="string"
            )
        else:
            piece["kickoff_time"] = pd.Series(pd.NA, index=piece.index, dtype="string")
        piece["kickoff_timezone"] = str(CANONICAL_TIMEZONE)
        piece["kickoff_time_source"] = pd.Series(pd.NA, index=piece.index, dtype="string")
        piece.loc[
            piece["kickoff_time"].notna(), "kickoff_time_source"
        ] = "football_data_europe_london_converted"
        piece["tff_match_id"] = pd.Series(pd.NA, index=piece.index, dtype="string")
        piece["official_home_goals"] = pd.Series(pd.NA, index=piece.index, dtype="Int64")
        piece["official_away_goals"] = pd.Series(pd.NA, index=piece.index, dtype="Int64")
        piece["official_result"] = pd.Series(pd.NA, index=piece.index, dtype="string")

        for canonical, source in OPTIONAL_FIELD_MAP.items():
            if source not in raw:
                piece[canonical] = pd.Series(pd.NA, index=piece.index, dtype="Int64")
            else:
                piece[canonical] = pd.to_numeric(raw[source], errors="coerce").astype("Int64")
        pieces.append(piece)

    matches = pd.concat(pieces, ignore_index=True)
    status_key = ["season", "date", "home_team_raw", "away_team_raw"]
    status = overrides[
        [
            "season",
            "date_iso",
            "home_team_raw",
            "away_team_raw",
            "match_status",
            "model_eligible",
        ]
    ].rename(columns={"date_iso": "date"})
    matches = matches.merge(status, on=status_key, how="left", validate="one_to_one")
    matches["match_status"] = matches["match_status"].fillna("played")
    matches["model_eligible"] = matches["model_eligible"].map(
        {"true": True, "false": False}
    )
    matches["model_eligible"] = matches["model_eligible"].fillna(True).astype(bool)
    return matches


def apply_tff_kickoffs(matches: pd.DataFrame, tff: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    join_key = ["season", "home_team", "away_team"]
    tff_for_join = tff[
        [
            *join_key,
            "date",
            "kickoff_time",
            "home_goals",
            "away_goals",
            "tff_match_id",
        ]
    ].rename(
        columns={
            "date": "tff_date",
            "kickoff_time": "tff_kickoff_time",
            "home_goals": "tff_home_goals",
            "away_goals": "tff_away_goals",
            "tff_match_id": "tff_match_id_backfill",
        }
    )
    merged = matches.merge(tff_for_join, on=join_key, how="left", validate="one_to_one")
    early = merged["season"].isin(EARLY_KICKOFF_SEASONS)
    if merged.loc[early, "tff_kickoff_time"].isna().any():
        missing = merged.loc[early & merged["tff_kickoff_time"].isna(), join_key]
        raise CanonicalBuildError(
            "TFF kickoff join missed Football-Data rows: "
            f"{missing.head(10).to_dict(orient='records')}"
        )
    if merged.loc[~early, "tff_kickoff_time"].notna().any():
        raise CanonicalBuildError("TFF kickoff snapshot unexpectedly matched a later season")
    if not KICKOFF_DATE_DISCREPANCIES.exists() or not KICKOFF_REVIEW_SOURCES.exists():
        raise CanonicalBuildError("Missing reviewed kickoff-date discrepancy config")
    discrepancies = pd.read_csv(KICKOFF_DATE_DISCREPANCIES, dtype="string")
    review_sources = pd.read_csv(KICKOFF_REVIEW_SOURCES, dtype="string")
    review_source_columns = {"evidence_id", "authority", "title", "url", "accessed_date"}
    if not review_source_columns.issubset(review_sources.columns):
        raise CanonicalBuildError("Kickoff review-source config has an unexpected schema")
    if review_sources[list(review_source_columns)].isna().any(axis=None):
        raise CanonicalBuildError("Kickoff review-source config has null required values")
    if review_sources["evidence_id"].duplicated().any():
        raise CanonicalBuildError("Kickoff review-source evidence IDs are duplicated")
    discrepancy_columns = [
        "season",
        "football_data_date",
        "tff_date",
        "home_team",
        "away_team",
        "decision",
        "evidence_ids",
    ]
    if discrepancies[discrepancy_columns].isna().any(axis=None):
        raise CanonicalBuildError("Kickoff-date discrepancy config has null required values")
    if set(discrepancies["decision"]) != {"retain_original_kickoff_date"}:
        raise CanonicalBuildError("Unexpected kickoff-date discrepancy decision")
    known_evidence = set(review_sources["evidence_id"])
    if not TIMEZONE_EVIDENCE_IDS.issubset(known_evidence):
        raise CanonicalBuildError("Missing TFF evidence for kickoff timezone conversion")
    referenced_evidence: set[str] = set()
    for value in discrepancies["evidence_ids"]:
        referenced_evidence.update(str(value).split("|"))
    if referenced_evidence - known_evidence:
        raise CanonicalBuildError(
            "Kickoff-date discrepancy references unknown evidence IDs: "
            f"{sorted(referenced_evidence - known_evidence)}"
        )
    date_mismatch = early & merged["date"].ne(merged["tff_date"])
    observed_date_mismatches = set(
        map(
            tuple,
            merged.loc[
                date_mismatch,
                ["season", "date", "tff_date", "home_team", "away_team"],
            ].itertuples(index=False, name=None),
        )
    )
    reviewed_date_mismatches = set(
        map(
            tuple,
            discrepancies[
                [
                    "season",
                    "football_data_date",
                    "tff_date",
                    "home_team",
                    "away_team",
                ]
            ].itertuples(index=False, name=None),
        )
    )
    if observed_date_mismatches != reviewed_date_mismatches:
        raise CanonicalBuildError(
            "Kickoff-date discrepancy set changed. "
            f"Unreviewed={sorted(observed_date_mismatches - reviewed_date_mismatches)}; "
            f"stale_reviews={sorted(reviewed_date_mismatches - observed_date_mismatches)}"
        )
    score_mismatch = early & (
        merged["home_goals"].ne(merged["tff_home_goals"])
        | merged["away_goals"].ne(merged["tff_away_goals"])
    )
    if not KICKOFF_SCORE_DISCREPANCIES.exists():
        raise CanonicalBuildError("Missing reviewed kickoff-score discrepancy config")
    score_reviews = pd.read_csv(KICKOFF_SCORE_DISCREPANCIES, dtype="string")
    required_score_review_columns = [
        "season",
        "date",
        "home_team",
        "away_team",
        "on_pitch_home_goals",
        "on_pitch_away_goals",
        "official_home_goals",
        "official_away_goals",
        "match_status",
        "model_eligible",
        "decision",
        "evidence_ids",
    ]
    if score_reviews[required_score_review_columns].isna().any(axis=None):
        raise CanonicalBuildError("Kickoff-score discrepancy config has null required values")
    if set(score_reviews["decision"]) != {"retain_on_pitch_score_for_score_models"}:
        raise CanonicalBuildError("Unexpected kickoff-score discrepancy decision")
    if set(score_reviews["match_status"]) != {"played_then_awarded_forfeit"}:
        raise CanonicalBuildError("Unexpected reviewed played-match status")
    if set(score_reviews["model_eligible"]) != {"true"}:
        raise CanonicalBuildError("Reviewed played score discrepancy must remain model eligible")
    for value in score_reviews["evidence_ids"]:
        referenced_evidence.update(str(value).split("|"))
    if referenced_evidence - known_evidence:
        raise CanonicalBuildError(
            "Kickoff discrepancy config references unknown evidence IDs: "
            f"{sorted(referenced_evidence - known_evidence)}"
        )

    observed_score_mismatches = set(
        map(
            tuple,
            merged.loc[
                score_mismatch,
                [
                    "season",
                    "date",
                    "home_team",
                    "away_team",
                    "home_goals",
                    "away_goals",
                    "tff_home_goals",
                    "tff_away_goals",
                ],
            ].itertuples(index=False, name=None),
        )
    )
    reviewed_score_mismatches = set(
        (
            row.season,
            row.date,
            row.home_team,
            row.away_team,
            int(row.on_pitch_home_goals),
            int(row.on_pitch_away_goals),
            int(row.official_home_goals),
            int(row.official_away_goals),
        )
        for row in score_reviews.itertuples(index=False)
    )
    if observed_score_mismatches != reviewed_score_mismatches:
        raise CanonicalBuildError(
            "Kickoff-score discrepancy set changed. "
            f"Unreviewed={sorted(observed_score_mismatches - reviewed_score_mismatches)}; "
            f"stale_reviews={sorted(reviewed_score_mismatches - observed_score_mismatches)}"
        )

    score_review_key = ["season", "date", "home_team", "away_team"]
    score_review_payload = score_reviews[
        [
            *score_review_key,
            "official_home_goals",
            "official_away_goals",
            "match_status",
        ]
    ].rename(
        columns={
            "official_home_goals": "reviewed_official_home_goals",
            "official_away_goals": "reviewed_official_away_goals",
            "match_status": "reviewed_match_status",
        }
    )
    merged = merged.merge(
        score_review_payload,
        on=score_review_key,
        how="left",
        validate="one_to_one",
    )
    reviewed_score = merged["reviewed_match_status"].notna()
    merged.loc[reviewed_score, "official_home_goals"] = pd.to_numeric(
        merged.loc[reviewed_score, "reviewed_official_home_goals"], errors="raise"
    ).astype("Int64")
    merged.loc[reviewed_score, "official_away_goals"] = pd.to_numeric(
        merged.loc[reviewed_score, "reviewed_official_away_goals"], errors="raise"
    ).astype("Int64")
    official_expected = audit.expected_result(
        pd.to_numeric(merged["official_home_goals"], errors="coerce"),
        pd.to_numeric(merged["official_away_goals"], errors="coerce"),
    )
    merged.loc[reviewed_score, "official_result"] = official_expected.loc[reviewed_score]
    merged.loc[reviewed_score, "match_status"] = merged.loc[
        reviewed_score, "reviewed_match_status"
    ]

    merged.loc[early, "kickoff_time"] = merged.loc[early, "tff_kickoff_time"]
    merged.loc[early, "kickoff_time_source"] = "tff_archive"
    merged.loc[early, "tff_match_id"] = merged.loc[
        early, "tff_match_id_backfill"
    ].astype("string")

    join_rows: list[dict[str, Any]] = []
    for season in sorted(EARLY_KICKOFF_SEASONS):
        selected = merged[merged["season"] == season]
        join_rows.append(
            {
                "season": season,
                "football_data_rows": len(selected),
                "tff_snapshot_rows": int((tff["season"] == season).sum()),
                "matched_rows": int(selected["tff_kickoff_time"].notna().sum()),
                "unmatched_rows": int(selected["tff_kickoff_time"].isna().sum()),
                "reviewed_date_mismatches": int(date_mismatch.loc[selected.index].sum()),
                "reviewed_score_differences": int(score_mismatch.loc[selected.index].sum()),
                "duplicate_canonical_keys": int(selected.duplicated(join_key).sum()),
            }
        )

    merged = merged.drop(
        columns=[
            "tff_kickoff_time",
            "tff_date",
            "tff_home_goals",
            "tff_away_goals",
            "tff_match_id_backfill",
            "reviewed_official_home_goals",
            "reviewed_official_away_goals",
            "reviewed_match_status",
        ]
    )
    return merged, pd.DataFrame(join_rows)


def finalize_matches(matches: pd.DataFrame) -> pd.DataFrame:
    matches = matches.copy()
    matches["match_id"] = [
        stable_match_id(season, date, home, away)
        for season, date, home, away in matches[
            ["season", "date", "home_team", "away_team"]
        ].itertuples(index=False, name=None)
    ]
    natural_key = ["season", "date", "home_team", "away_team"]
    required = [
        "match_id",
        *natural_key,
        "kickoff_time",
        "kickoff_timezone",
        "kickoff_time_source",
        "home_goals",
        "away_goals",
        "result",
        "match_status",
        "model_eligible",
    ]
    if matches[required].isna().any(axis=None):
        nulls = matches[required].isna().sum()
        raise CanonicalBuildError(f"Canonical required fields contain nulls: {nulls[nulls > 0].to_dict()}")
    if matches.duplicated(natural_key).any() or matches["match_id"].duplicated().any():
        raise CanonicalBuildError("Canonical match IDs or natural keys are duplicated")
    if (matches["home_team"] == matches["away_team"]).any():
        raise CanonicalBuildError("Canonical data contains a same-team match")
    expected = audit.expected_result(matches["home_goals"], matches["away_goals"])
    if matches["result"].ne(expected).any():
        raise CanonicalBuildError("Canonical results disagree with canonical scores")
    parsed_kickoffs = pd.to_datetime(
        matches["kickoff_time"], format="%H:%M", errors="coerce"
    )
    if parsed_kickoffs.isna().any():
        raise CanonicalBuildError("Canonical kickoff times contain invalid values")
    if len(matches) != 3088 or int((~matches["model_eligible"]).sum()) != 31:
        raise CanonicalBuildError(
            "Canonical row or reviewed-exclusion count changed unexpectedly"
        )
    if int((matches["match_status"] == "not_played_forfeit").sum()) != 29:
        raise CanonicalBuildError("Expected 29 not-played forfeits")
    if int((matches["match_status"] == "abandoned_forfeit").sum()) != 2:
        raise CanonicalBuildError("Expected two abandoned forfeits")
    if int((matches["match_status"] == "played_then_awarded_forfeit").sum()) != 1:
        raise CanonicalBuildError("Expected one played-then-awarded forfeit")
    allowed_statuses = {
        "played",
        "not_played_forfeit",
        "abandoned_forfeit",
        "played_then_awarded_forfeit",
    }
    if set(matches["match_status"]) != allowed_statuses:
        raise CanonicalBuildError("Canonical match-status values changed unexpectedly")
    expected_eligibility = ~matches["match_status"].isin(
        {"not_played_forfeit", "abandoned_forfeit"}
    )
    if not matches["model_eligible"].eq(expected_eligibility).all():
        raise CanonicalBuildError("Match status and model eligibility disagree")
    official_fields = ["official_home_goals", "official_away_goals", "official_result"]
    complete_official_score = matches[official_fields].notna().all(axis=1)
    partial_official_score = (
        matches[official_fields].notna().any(axis=1) & ~complete_official_score
    )
    if partial_official_score.any():
        raise CanonicalBuildError("Official-score override fields are only partially populated")
    if int(complete_official_score.sum()) != 1:
        raise CanonicalBuildError("Expected one complete official-score override")

    season_order = {season: index for index, season in enumerate(audit.SEASONS)}
    matches["_season_order"] = matches["season"].map(season_order)
    matches = matches.sort_values(
        ["_season_order", "date", "kickoff_time", "home_team", "away_team"],
        kind="stable",
    ).drop(columns="_season_order")
    matches["source_row"] = matches["source_row"].astype("int64")
    return matches[CANONICAL_COLUMNS].reset_index(drop=True)


def build_market_benchmark(
    frames: OrderedDict[str, pd.DataFrame], canonical: pd.DataFrame
) -> pd.DataFrame:
    lookup = canonical[["season", "source_row", "match_id", "model_eligible"]]
    pieces: list[pd.DataFrame] = []
    for season, raw in frames.items():
        if season in EARLY_KICKOFF_SEASONS:
            fields = ("PSCH", "PSCD", "PSCA")
            tier = "secondary_single_bookmaker"
            regime = "pinnacle_closing"
            source = "Pinnacle closing (PSCH/PSCD/PSCA)"
        else:
            fields = ("AvgCH", "AvgCD", "AvgCA")
            tier = "primary_market_average"
            regime = "market_average_closing"
            source = "Football-Data closing market average (AvgCH/AvgCD/AvgCA)"
        if not set(fields).issubset(raw.columns):
            raise CanonicalBuildError(f"{season}: expected benchmark odds fields are absent")

        odds = pd.DataFrame(
            {
                "season": season,
                "source_row": raw.index.to_series().astype("int64") + 2,
                "closing_home_odds": pd.to_numeric(raw[fields[0]], errors="coerce"),
                "closing_draw_odds": pd.to_numeric(raw[fields[1]], errors="coerce"),
                "closing_away_odds": pd.to_numeric(raw[fields[2]], errors="coerce"),
            }
        ).merge(lookup, on=["season", "source_row"], how="left", validate="one_to_one")
        if odds[["match_id", "model_eligible"]].isna().any(axis=None):
            raise CanonicalBuildError(f"{season}: benchmark-to-canonical lookup failed")
        odds_fields = ["closing_home_odds", "closing_draw_odds", "closing_away_odds"]
        complete = odds[odds_fields].notna().all(axis=1)
        partial = odds[odds_fields].notna().any(axis=1) & ~complete
        if partial.any():
            raise CanonicalBuildError(f"{season}: benchmark odds contain partial H/D/A triplets")
        selected = odds.loc[odds["model_eligible"] & complete].copy()
        if selected[odds_fields].le(1.0).any(axis=None):
            raise CanonicalBuildError(f"{season}: decimal benchmark odds must be greater than one")

        inverse = 1.0 / selected[odds_fields]
        inverse_sum = inverse.sum(axis=1)
        selected["market_p_home"] = inverse["closing_home_odds"] / inverse_sum
        selected["market_p_draw"] = inverse["closing_draw_odds"] / inverse_sum
        selected["market_p_away"] = inverse["closing_away_odds"] / inverse_sum
        selected["market_overround"] = inverse_sum - 1.0
        selected["benchmark_tier"] = tier
        selected["benchmark_regime"] = regime
        selected["odds_source"] = source
        pieces.append(selected[MARKET_COLUMNS])

    market = pd.concat(pieces, ignore_index=True)
    if market["match_id"].duplicated().any():
        raise CanonicalBuildError("Market benchmark contains duplicate match IDs")
    if not set(market["match_id"]).issubset(set(canonical["match_id"])):
        raise CanonicalBuildError("Market benchmark contains orphan match IDs")
    probability_sum = market[["market_p_home", "market_p_draw", "market_p_away"]].sum(axis=1)
    if not probability_sum.sub(1.0).abs().lt(1e-12).all():
        raise CanonicalBuildError("De-vigged market probabilities do not sum to one")
    return market.sort_values(["season", "match_id"], kind="stable").reset_index(drop=True)


def quality_by_season(canonical: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    market_counts = market.groupby("season").size()
    rows: list[dict[str, Any]] = []
    for season in audit.SEASONS:
        selected = canonical[canonical["season"] == season]
        eligible = int(selected["model_eligible"].sum())
        benchmark_rows = int(market_counts.get(season, 0))
        regimes = sorted(set(market.loc[market["season"] == season, "benchmark_regime"]))
        rows.append(
            {
                "season": season,
                "match_rows": len(selected),
                "model_eligible_rows": eligible,
                "excluded_administrative_rows": int((~selected["model_eligible"]).sum()),
                "kickoff_complete_rows": int(selected["kickoff_time"].notna().sum()),
                "tff_backfill_rows": int((selected["kickoff_time_source"] == "tff_archive").sum()),
                "market_benchmark_rows": benchmark_rows,
                "market_coverage_of_eligible": benchmark_rows / eligible if eligible else 0.0,
                "benchmark_regime": "|".join(regimes),
            }
        )
    return pd.DataFrame(rows)


def generate_report(
    canonical: pd.DataFrame,
    market: pd.DataFrame,
    quality: pd.DataFrame,
    join_audit: pd.DataFrame,
) -> str:
    eligible = int(canonical["model_eligible"].sum())
    primary = int((market["benchmark_tier"] == "primary_market_average").sum())
    secondary = int((market["benchmark_tier"] == "secondary_single_bookmaker").sum())
    table_rows = []
    for row in quality.itertuples(index=False):
        table_rows.append(
            [
                row.season,
                row.match_rows,
                row.model_eligible_rows,
                row.excluded_administrative_rows,
                row.kickoff_complete_rows,
                row.tff_backfill_rows,
                row.market_benchmark_rows,
                audit.pct(row.market_coverage_of_eligible),
                row.benchmark_regime,
            ]
        )
    join_rows = [
        [
            row.season,
            row.football_data_rows,
            row.tff_snapshot_rows,
            row.matched_rows,
            row.unmatched_rows,
            row.reviewed_date_mismatches,
            row.reviewed_score_differences,
            row.duplicate_canonical_keys,
        ]
        for row in join_audit.itertuples(index=False)
    ]
    lines = [
        "# Canonical data build audit",
        "",
        "## Answer first",
        "",
        "**GO.** The canonical match table contains all 3,088 audited fixtures,",
        f"including {eligible:,} played-match-eligible rows and 31 source-reviewed",
        "administrative exclusions. Kickoff time is complete for every row after an",
        "exact one-to-one, score-verified TFF backfill of the first two seasons and",
        "timezone-aware Europe/London-to-Europe/Istanbul conversion thereafter.",
        "",
        f"The isolated market benchmark contains {len(market):,} rows: {primary:,}",
        "primary closing-market-average rows from 2019-20 onward and",
        f"{secondary:,} separately labelled Pinnacle-closing rows for 2017-18 and",
        "2018-19. Three eligible 2017-18 matches have no complete Pinnacle triplet",
        "and remain absent from the benchmark rather than being imputed.",
        "",
        "No predictive feature, baseline, Poisson model, or Dixon-Coles model is built",
        "in this phase.",
        "",
        "## Coverage by season",
        "",
        audit.md_table(
            [
                "Season",
                "Matches",
                "Eligible",
                "Excluded",
                "Kickoff complete",
                "TFF backfill",
                "Market rows",
                "Market coverage",
                "Regime",
            ],
            table_rows,
        ),
        "",
        "## TFF kickoff join checks",
        "",
        audit.md_table(
            [
                "Season",
                "Football-Data rows",
                "TFF rows",
                "Matched",
                "Unmatched",
                "Reviewed date differences",
                "Reviewed score differences",
                "Duplicate keys",
            ],
            join_rows,
        ),
        "",
        "TFF names are mapped only through `config/tff_team_aliases.csv`. The build",
        "fails on an unseen TFF label, duplicate canonical key, unmatched fixture, or",
        "score disagreement. The single source-date difference is explicitly reviewed:",
        "Başakşehir-Bursaspor retains its original 23 February prediction timestamp",
        "after the weather suspension and next-day continuation. The played",
        "Akhisarspor-Beşiktaş score remains 1-3 for score modeling while the official",
        "0-3 PFDK result is preserved in separate fields. The immutable",
        "Football-Data CSVs are never rewritten.",
        "Two official 2019-20 TFF weeks lock the summer and winter timezone behavior",
        "so British daylight-saving transitions are not represented as Turkish time.",
        "",
        "## Leakage and benchmark boundary",
        "",
        "`canonical_matches.csv` contains historical match outcomes, not a feature",
        "matrix. Current-match outcomes remain forbidden predictive inputs under",
        "`LEAKAGE_CONTRACT.md`. `market_benchmark.csv` is a separate table and may be",
        "joined only after model predictions are frozen.",
        "An earlier kickoff is not treated as an available result until the future",
        "evaluation code applies the completion rule in `LEAKAGE_CONTRACT.md`.",
        "",
        "## Remaining modeling work",
        "",
        "Chronological evaluation scaffolding, naive baselines, independent Poisson,",
        "time-decayed Dixon-Coles, and the dynamic promoted-team prior remain",
        "unimplemented. Their design boundary is recorded in `MODEL_DESIGN.md`.",
        "The conservative result-availability lag must be frozen before evaluation.",
        "",
        "## Reviewed source links",
        "",
        "- [TFF 2019-20 week 1](https://www.tff.org/Default.aspx?hafta=1&pageID=1501)",
        "  verifies the summer UK-to-Turkey clock difference.",
        "- [TFF 2019-20 week 18](https://www.tff.org/Default.aspx?hafta=18&pageID=1501)",
        "  verifies the winter UK-to-Turkey clock difference.",
        "- Exact acquisition and discrepancy evidence is catalogued in",
        "  `data/raw/tff/kickoff_times_2017-19.manifest.json` and",
        "  `config/kickoff_review_sources.csv`.",
    ]
    return "\n".join(lines)


def write_outputs(
    canonical: pd.DataFrame,
    market: pd.DataFrame,
    quality: pd.DataFrame,
    join_audit: pd.DataFrame,
) -> None:
    audit.write_csv(CANONICAL_MATCHES, canonical)
    audit.write_csv(MARKET_BENCHMARK, market)
    audit.write_csv(QUALITY_BY_SEASON, quality)
    audit.write_csv(TFF_JOIN_AUDIT, join_audit)
    audit.write_text(QUALITY_REPORT, generate_report(canonical, market, quality, join_audit))


def main() -> int:
    try:
        sources = audit.load_source_catalog()
        manifest = audit.ensure_raw_sources(sources, offline=True)
        frames = audit.read_raw_frames(sources)
        audit.lock_or_validate_schemas(frames, write_schema_lock=False)
        evidence = audit.build_evidence(frames, manifest)
        tff, _ = validate_tff_snapshot()
        base = build_base_matches(frames)
        with_kickoffs, join_audit = apply_tff_kickoffs(base, tff)
        canonical = finalize_matches(with_kickoffs)
        market = build_market_benchmark(frames, canonical)
        quality = quality_by_season(canonical, market)
        write_outputs(canonical, market, quality, join_audit)
        print(
            "Canonical build complete: "
            f"{len(canonical)} matches, {int(canonical['model_eligible'].sum())} eligible, "
            f"{len(market)} market benchmark rows."
        )
        print(f"Report: {QUALITY_REPORT}")
        print("Verdict: GO")
        return 0
    except (audit.AuditError, CanonicalBuildError, ValueError) as exc:
        print(f"CANONICAL BUILD FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
