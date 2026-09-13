#!/usr/bin/env python3
"""Acquire an immutable TFF-derived kickoff snapshot for 2017-18 and 2018-19."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONFIG = ROOT / "config" / "kickoff_sources.csv"
RAW_DIR = ROOT / "data" / "raw" / "tff"
SNAPSHOT = RAW_DIR / "kickoff_times_2017-19.csv"
MANIFEST = RAW_DIR / "kickoff_times_2017-19.manifest.json"

USER_AGENT = "AI-SuperLig-Research/1.0 (+public reproducible data audit)"
ROW_PATTERN = re.compile(
    r'<tr\s+class=["\']haftaninMaclariTr["\']>(.*?)</tr>',
    flags=re.IGNORECASE | re.DOTALL,
)


class BootstrapError(RuntimeError):
    """A source or validation failure that must stop acquisition."""


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_tff_html(content: bytes) -> str:
    """Decode current and historical TFF pages without lossy replacement."""
    for encoding in ("utf-8", "windows-1254", "iso-8859-9"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise BootstrapError("TFF HTML could not be decoded without replacement characters")


def clean_html_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(without_tags).split())


def span_value(block: str, id_suffix: str) -> str:
    pattern = re.compile(
        rf'<span\s+id=["\'][^"\']*{re.escape(id_suffix)}["\']>(.*?)</span>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(block)
    if not match:
        raise BootstrapError(f"Missing TFF span ending in {id_suffix}")
    return clean_html_text(match.group(1))


def parse_week_html(
    *, season: str, week: int, source_url: str, content: bytes
) -> list[dict[str, Any]]:
    decoded = decode_tff_html(content)
    blocks = ROW_PATTERN.findall(decoded)
    rows: list[dict[str, Any]] = []
    for block in blocks:
        date_value = span_value(block, "lblTarih")
        time_value = span_value(block, "lblSaat")
        home_team = span_value(block, "Label4")
        home_goals = span_value(block, "Label5")
        away_goals = span_value(block, "Label6")
        away_team = span_value(block, "Label1")
        match_id_match = re.search(r"[?&](?:amp;)?macId=(\d+)", block, re.IGNORECASE)
        if not match_id_match:
            raise BootstrapError(
                f"Missing TFF match ID for {season} week {week}: "
                f"{home_team} - {away_team}"
            )

        parsed_date = datetime.strptime(date_value, "%d.%m.%Y").date()
        parsed_time = datetime.strptime(time_value, "%H:%M").time()
        rows.append(
            {
                "season": season,
                "week": week,
                "date": parsed_date.isoformat(),
                "kickoff_time": parsed_time.strftime("%H:%M"),
                "home_team_tff": home_team,
                "away_team_tff": away_team,
                "home_goals": int(home_goals),
                "away_goals": int(away_goals),
                "tff_match_id": match_id_match.group(1),
                "source_url": source_url,
            }
        )
    return rows


def validate_rows(rows: pd.DataFrame, sources: pd.DataFrame) -> None:
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
    if rows.columns.tolist() != expected_columns:
        raise BootstrapError(f"Unexpected snapshot columns: {rows.columns.tolist()}")
    if rows[expected_columns].isna().any(axis=None):
        raise BootstrapError("TFF kickoff extraction contains null required values")
    if rows["tff_match_id"].astype("string").duplicated().any():
        raise BootstrapError("TFF kickoff extraction contains duplicate match IDs")
    natural_key = ["season", "date", "home_team_tff", "away_team_tff"]
    if rows.duplicated(natural_key).any():
        raise BootstrapError("TFF kickoff extraction contains duplicate match keys")
    parsed_dates = pd.to_datetime(rows["date"], format="%Y-%m-%d", errors="coerce")
    parsed_times = pd.to_datetime(rows["kickoff_time"], format="%H:%M", errors="coerce")
    if parsed_dates.isna().any() or parsed_times.isna().any():
        raise BootstrapError("TFF kickoff extraction contains invalid dates or times")
    if (rows["home_team_tff"].str.strip() == rows["away_team_tff"].str.strip()).any():
        raise BootstrapError("TFF kickoff extraction contains a same-team fixture")

    for source in sources.itertuples(index=False):
        selected = rows[rows["season"] == source.season]
        if len(selected) != int(source.expected_matches):
            raise BootstrapError(
                f"{source.season}: expected {source.expected_matches} matches, "
                f"extracted {len(selected)}"
            )
        expected_weeks = set(range(int(source.first_week), int(source.last_week) + 1))
        actual_weeks = set(selected["week"].astype(int))
        if actual_weeks != expected_weeks:
            raise BootstrapError(
                f"{source.season}: week coverage changed; "
                f"missing={sorted(expected_weeks - actual_weeks)}, "
                f"extra={sorted(actual_weeks - expected_weeks)}"
            )
        weekly_counts = selected.groupby("week").size()
        if not weekly_counts.eq(9).all():
            raise BootstrapError(
                f"{source.season}: expected nine matches in every week; "
                f"found={weekly_counts.to_dict()}"
            )


def load_config() -> pd.DataFrame:
    if not SOURCE_CONFIG.exists():
        raise BootstrapError(f"Missing kickoff source config: {SOURCE_CONFIG}")
    sources = pd.read_csv(SOURCE_CONFIG, dtype={"season": "string"})
    required = {
        "season",
        "page_id",
        "first_week",
        "last_week",
        "expected_matches",
        "timezone",
        "source_url_template",
    }
    missing = required.difference(sources.columns)
    if missing:
        raise BootstrapError(f"Kickoff source config missing columns: {sorted(missing)}")
    if sources["season"].tolist() != ["2017-18", "2018-19"]:
        raise BootstrapError("Kickoff source seasons or order changed unexpectedly")
    return sources


def fetch(session: requests.Session, url: str, retries: int = 3) -> bytes:
    failure: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, timeout=(20, 60))
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "html" not in content_type:
                raise BootstrapError(f"Unexpected TFF content type for {url}: {content_type}")
            if b"haftaninMaclariTr" not in response.content:
                raise BootstrapError(f"Expected TFF fixture table is absent: {url}")
            return response.content
        except (requests.RequestException, BootstrapError) as exc:
            failure = exc
            if attempt < retries:
                time.sleep(float(attempt))
    raise BootstrapError(f"TFF request failed after {retries} attempts: {url}: {failure}")


def write_snapshot(rows: pd.DataFrame, page_manifest: list[dict[str, Any]]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    csv_temp = SNAPSHOT.with_suffix(SNAPSHOT.suffix + ".download")
    manifest_temp = MANIFEST.with_suffix(MANIFEST.suffix + ".download")
    if SNAPSHOT.exists() or MANIFEST.exists() or csv_temp.exists() or manifest_temp.exists():
        raise BootstrapError(
            "TFF snapshot, manifest, or incomplete download already exists; "
            "refusing to overwrite immutable acquisition files"
        )

    csv_buffer = io.StringIO(newline="")
    rows.to_csv(csv_buffer, index=False, lineterminator="\n")
    csv_bytes = csv_buffer.getvalue().encode("utf-8")
    acquired_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    manifest_payload = {
        "description": "Immutable source-derived TFF kickoff snapshot for Football-Data seasons without Time.",
        "acquired_at_utc": acquired_at,
        "snapshot_path": SNAPSHOT.relative_to(ROOT).as_posix(),
        "snapshot_sha256": sha256_bytes(csv_bytes),
        "snapshot_bytes": len(csv_bytes),
        "row_count": len(rows),
        "source_pages": page_manifest,
    }
    manifest_bytes = (
        json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")

    try:
        with csv_temp.open("xb") as handle:
            handle.write(csv_bytes)
        with manifest_temp.open("xb") as handle:
            handle.write(manifest_bytes)
        os.replace(csv_temp, SNAPSHOT)
        os.replace(manifest_temp, MANIFEST)
    except Exception:
        for path in (csv_temp, manifest_temp):
            if path.exists():
                path.unlink()
        raise


def validate_existing_snapshot() -> None:
    if SNAPSHOT.exists() != MANIFEST.exists():
        raise BootstrapError("TFF snapshot and manifest must either both exist or both be absent")
    if not SNAPSHOT.exists():
        return
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if sha256_file(SNAPSHOT) != manifest.get("snapshot_sha256"):
        raise BootstrapError("Immutable TFF kickoff snapshot checksum mismatch")
    if SNAPSHOT.stat().st_size != int(manifest.get("snapshot_bytes", -1)):
        raise BootstrapError("Immutable TFF kickoff snapshot byte-size mismatch")
    rows = pd.read_csv(SNAPSHOT, dtype={"season": "string", "tff_match_id": "string"})
    validate_rows(rows, load_config())
    print(f"Existing TFF kickoff snapshot is valid: {len(rows)} rows")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the immutable TFF-derived kickoff snapshot once."
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=0.20,
        help="Delay in seconds between TFF requests (default: 0.20).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        sources = load_config()
        if SNAPSHOT.exists() or MANIFEST.exists():
            validate_existing_snapshot()
            return 0

        rows: list[dict[str, Any]] = []
        page_manifest: list[dict[str, Any]] = []
        with requests.Session() as session:
            session.headers.update({"User-Agent": USER_AGENT})
            for source in sources.itertuples(index=False):
                for week in range(int(source.first_week), int(source.last_week) + 1):
                    url = str(source.source_url_template).format(week=week)
                    content = fetch(session, url)
                    week_rows = parse_week_html(
                        season=str(source.season),
                        week=week,
                        source_url=url,
                        content=content,
                    )
                    rows.extend(week_rows)
                    page_manifest.append(
                        {
                            "season": str(source.season),
                            "week": week,
                            "url": url,
                            "response_sha256": sha256_bytes(content),
                            "response_bytes": len(content),
                            "match_rows": len(week_rows),
                        }
                    )
                    if args.request_delay > 0:
                        time.sleep(args.request_delay)

        frame = pd.DataFrame(rows)
        validate_rows(frame, sources)
        write_snapshot(frame, page_manifest)
        validate_existing_snapshot()
        print(f"Created TFF kickoff snapshot: {SNAPSHOT}")
        return 0
    except (BootstrapError, ValueError) as exc:
        print(f"TFF KICKOFF BOOTSTRAP FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
