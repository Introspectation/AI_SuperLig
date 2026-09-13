from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap_tff_kickoffs as bootstrap  # noqa: E402


SAMPLE_HTML = b"""
<html><body>
<table>
<tr class="haftaninMaclariTr">
  <td><span id="fixture_ctl01_lblTarih">10.08.2018</span>
      <span id="fixture_ctl01_lblSaat">21:45</span></td>
  <td><span id="fixture_ctl01_Label4">MKE ANKARAG\xc3\x9cC\xc3\x9c</span></td>
  <td><a href="Default.aspx?pageId=29&amp;macId=194516">
      <span id="fixture_ctl01_Label5">1</span> -
      <span id="fixture_ctl01_Label6">3</span></a></td>
  <td><span id="fixture_ctl01_Label1">GALATASARAY A.\xc5\x9e.</span></td>
</tr>
</table>
</body></html>
"""


class TffKickoffBootstrapTests(unittest.TestCase):
    def test_parse_week_html_preserves_turkish_names_and_identity(self) -> None:
        rows = bootstrap.parse_week_html(
            season="2018-19",
            week=1,
            source_url="https://www.tff.org/example",
            content=SAMPLE_HTML,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2018-08-10")
        self.assertEqual(rows[0]["kickoff_time"], "21:45")
        self.assertEqual(rows[0]["home_team_tff"], "MKE ANKARAG\u00dcC\u00dc")
        self.assertEqual(rows[0]["away_team_tff"], "GALATASARAY A.\u015e.")
        self.assertEqual(rows[0]["home_goals"], 1)
        self.assertEqual(rows[0]["away_goals"], 3)
        self.assertEqual(rows[0]["tff_match_id"], "194516")


if __name__ == "__main__":
    unittest.main()
