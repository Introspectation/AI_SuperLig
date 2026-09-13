from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_data_audit as audit  # noqa: E402
import check_current_season_freshness as freshness  # noqa: E402
import promote_current_season_snapshot as promotion  # noqa: E402


class DataAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = audit.load_source_catalog()
        cls.manifest = audit.ensure_raw_sources(cls.sources, offline=True)
        cls.frames = audit.read_raw_frames(cls.sources)
        cls.evidence = audit.build_evidence(cls.frames, cls.manifest)

    def test_catalog_has_exact_requested_seasons(self) -> None:
        self.assertEqual(self.sources["season"].tolist(), audit.SEASONS)
        self.assertEqual(len(self.manifest), 10)
        self.assertTrue(self.manifest["checksum_ok"].all())

    def test_schema_lock_matches_exact_ordered_columns(self) -> None:
        lock = json.loads(audit.SCHEMA_LOCK.read_text(encoding="utf-8"))
        actual = {season: frame.columns.tolist() for season, frame in self.frames.items()}
        self.assertEqual(lock["schemas"], actual)

    def test_match_grain_and_core_values_are_valid(self) -> None:
        summary = self.evidence["season_summary"]
        self.assertEqual(int(summary["row_count"].sum()), 3124)
        self.assertEqual(int(summary["exact_duplicate_rows"].sum()), 0)
        self.assertEqual(int(summary["duplicate_matches"].sum()), 0)
        self.assertEqual(int(summary["date_parsing_failures"].sum()), 0)
        self.assertEqual(int(summary["invalid_team_rows"].sum()), 0)
        self.assertEqual(int(summary["invalid_score_rows"].sum()), 0)
        self.assertEqual(int(summary["result_score_mismatches"].sum()), 0)

    def test_non_played_candidates_have_exact_source_backed_decisions(self) -> None:
        candidates = self.evidence["suspected_non_played_matches"]
        counts = candidates.groupby("season").size().to_dict()
        self.assertEqual(counts, {"2022-23": 29, "2023-24": 1, "2024-25": 1})
        self.assertTrue((candidates["review_status"] == "source_confirmed").all())
        self.assertFalse(candidates["model_eligible"].any())
        self.assertEqual(
            candidates["match_status"].value_counts().to_dict(),
            {"not_played_forfeit": 29, "abandoned_forfeit": 2},
        )

    def test_team_aliases_are_explicitly_approved_and_source_backed(self) -> None:
        aliases = self.evidence["team_aliases"]
        self.assertEqual(len(aliases), 7)
        self.assertEqual(set(aliases["confidence"]), {"high"})
        self.assertEqual(
            set(aliases["review_status"]), {"approved_for_canonicalization"}
        )
        self.assertFalse(aliases["evidence_ids"].str.strip().eq("").any())

    def test_legacy_vc_odds_are_not_misclassified_as_closing(self) -> None:
        triplets_2017 = audit.closing_bookmaker_triplets(self.frames["2017-18"])
        prefixes = [prefix for prefix, _ in triplets_2017]
        self.assertEqual(prefixes, ["PS"])
        self.assertNotIn("V", prefixes)
        self.assertNotIn("VC", prefixes)

    def test_market_average_closing_starts_in_2019_20(self) -> None:
        odds = self.evidence["odds_coverage_by_season"]
        closing = odds[odds["odds_type"] == "closing_market_average_1x2"]
        self.assertEqual(closing["season"].tolist(), audit.SEASONS[2:])
        self.assertTrue(
            (closing[["home_column", "draw_column", "away_column"]]
             == ["AvgCH", "AvgCD", "AvgCA"]).all(axis=None)
        )

    def test_current_snapshot_is_immutable_audited_and_explicitly_stale(self) -> None:
        snapshots = self.evidence["current_season_snapshot_audit"]
        self.assertEqual(len(snapshots), 1)
        active = snapshots.iloc[0]
        self.assertTrue(active["is_active"])
        self.assertEqual(active["row_count"], 36)
        self.assertEqual(active["date_max"], "2026-09-07")
        self.assertEqual(active["capture_to_latest_match_days"], 6)
        self.assertEqual(active["freshness_status"], "REVIEW")
        self.assertEqual(active["added_match_keys"], 36)
        self.assertEqual(active["removed_match_keys"], 0)
        self.assertEqual(active["revised_shared_rows"], 0)

    def test_live_freshness_gate_checks_capture_age_and_required_coverage(self) -> None:
        ready = freshness.validate_freshness(
            as_of="2026-09-14T20:00:00+03:00",
            required_through="2026-09-07",
            max_capture_age_hours=24,
        )
        self.assertEqual(ready["date_max"], "2026-09-07")
        with self.assertRaises(freshness.FreshnessError):
            freshness.validate_freshness(
                as_of="2026-09-14T20:00:00+03:00",
                required_through="2026-09-13",
                max_capture_age_hours=24,
            )

    def test_snapshot_promotion_rejects_incomplete_coverage_before_writing(self) -> None:
        active = audit.active_current_snapshot()
        raw_path = audit.ROOT / active["raw_path"]
        catalog_before = audit.CURRENT_SNAPSHOT_CATALOG.read_bytes()
        raw_files_before = sorted(audit.RAW_DIR.glob(f"{audit.CURRENT_SEASON}__*.csv"))
        args = Namespace(
            input=str(raw_path),
            captured_at="2026-09-14T05:30:00Z",
            required_through="2026-09-13",
            acquisition_run_url="https://github.com/Introspectation/AI_SuperLig/actions/runs/1",
            artifact_name="test-artifact",
            artifact_digest="sha256:" + "0" * 64,
        )
        with self.assertRaises(promotion.PromotionError):
            promotion.promote(args)
        self.assertEqual(audit.CURRENT_SNAPSHOT_CATALOG.read_bytes(), catalog_before)
        self.assertEqual(
            sorted(audit.RAW_DIR.glob(f"{audit.CURRENT_SEASON}__*.csv")),
            raw_files_before,
        )

    def test_snapshot_promotion_appends_without_overwriting_prior_bytes(self) -> None:
        active = audit.active_current_snapshot()
        original_root = audit.ROOT
        original_raw_dir = audit.RAW_DIR
        original_catalog = audit.CURRENT_SNAPSHOT_CATALOG
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            temp_raw = temp_root / "data" / "raw" / "football_data"
            temp_config = temp_root / "config"
            temp_raw.mkdir(parents=True)
            temp_config.mkdir()
            prior = temp_root / active["raw_path"]
            shutil.copy2(original_root / active["raw_path"], prior)
            shutil.copy2(original_catalog, temp_config / original_catalog.name)
            audit.ROOT = temp_root
            audit.RAW_DIR = temp_raw
            audit.CURRENT_SNAPSHOT_CATALOG = temp_config / original_catalog.name
            try:
                result = promotion.promote(
                    Namespace(
                        input=str(prior),
                        captured_at="2026-09-14T05:30:00Z",
                        required_through="2026-09-07",
                        acquisition_run_url="https://github.com/Introspectation/AI_SuperLig/actions/runs/2",
                        artifact_name="test-artifact",
                        artifact_digest="sha256:" + "1" * 64,
                    )
                )
                updated = audit.load_current_snapshot_catalog()
                self.assertEqual(len(updated), 2)
                self.assertEqual(updated.iloc[-1]["snapshot_id"], result["snapshot_id"])
                self.assertTrue((temp_root / result["raw_path"]).exists())
                self.assertEqual(prior.read_bytes(), (temp_root / result["raw_path"]).read_bytes())
            finally:
                audit.ROOT = original_root
                audit.RAW_DIR = original_raw_dir
                audit.CURRENT_SNAPSHOT_CATALOG = original_catalog


if __name__ == "__main__":
    unittest.main()
