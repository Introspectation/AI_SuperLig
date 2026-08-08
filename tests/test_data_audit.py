from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_data_audit as audit  # noqa: E402


class DataAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = audit.load_source_catalog()
        cls.manifest = audit.ensure_raw_sources(cls.sources, offline=True)
        cls.frames = audit.read_raw_frames(cls.sources)
        cls.evidence = audit.build_evidence(cls.frames, cls.manifest)

    def test_catalog_has_exact_requested_seasons(self) -> None:
        self.assertEqual(self.sources["season"].tolist(), audit.SEASONS)
        self.assertEqual(len(self.manifest), 9)
        self.assertTrue(self.manifest["checksum_ok"].all())

    def test_schema_lock_matches_exact_ordered_columns(self) -> None:
        lock = json.loads(audit.SCHEMA_LOCK.read_text(encoding="utf-8"))
        actual = {season: frame.columns.tolist() for season, frame in self.frames.items()}
        self.assertEqual(lock["schemas"], actual)

    def test_match_grain_and_core_values_are_valid(self) -> None:
        summary = self.evidence["season_summary"]
        self.assertEqual(int(summary["row_count"].sum()), 3088)
        self.assertEqual(int(summary["exact_duplicate_rows"].sum()), 0)
        self.assertEqual(int(summary["duplicate_matches"].sum()), 0)
        self.assertEqual(int(summary["date_parsing_failures"].sum()), 0)
        self.assertEqual(int(summary["invalid_team_rows"].sum()), 0)
        self.assertEqual(int(summary["invalid_score_rows"].sum()), 0)
        self.assertEqual(int(summary["result_score_mismatches"].sum()), 0)

    def test_non_played_candidates_remain_explicit(self) -> None:
        candidates = self.evidence["suspected_non_played_matches"]
        counts = candidates.groupby("season").size().to_dict()
        self.assertEqual(counts, {"2022-23": 29, "2023-24": 1, "2024-25": 1})
        self.assertTrue((candidates["review_status"] == "human_review_required").all())

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


if __name__ == "__main__":
    unittest.main()
