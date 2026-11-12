import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from gazette.processing.report import collect_quality_snapshot, render_markdown, write_report


class QualityReportTests(unittest.TestCase):
    def test_snapshot_counts_and_top_rules(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchall.side_effect = [
            [("franceinfo", 4, 2, 2), ("lemonde", 2, 2, 0)],
            [("franceinfo", "R04_jeux_concours", 1), ("franceinfo", "R05_titre_vide", 1)],
        ]
        snapshot = collect_quality_snapshot(conn, generated_at=datetime(2026, 11, 12, tzinfo=UTC))
        self.assertEqual(
            snapshot["totaux"], {"entres": 6, "gardes": 4, "rejetes": 2, "non_classes": 0}
        )
        self.assertEqual(snapshot["par_source"][0]["taux_rejet_pct"], 50)
        self.assertEqual(snapshot["top_5_rejets"][0]["nombre"], 1)
        self.assertIn("R04_jeux_concours", render_markdown(snapshot))

    def test_no_items_and_pending_decision(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchall.side_effect = [[("lemonde", 1, 0, 0), ("vide", 0, 0, 0)], []]
        snapshot = collect_quality_snapshot(conn)
        self.assertEqual(snapshot["totaux"]["non_classes"], 1)
        self.assertIsNone(snapshot["par_source"][1]["taux_rejet_pct"])
        self.assertIn("sans décision qualité", render_markdown(snapshot))

    def test_archive_and_daily(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchall.side_effect = [[("franceinfo", 1, 1, 0)], []]
        snapshot = collect_quality_snapshot(
            conn, generated_at=datetime(2026, 11, 12, 9, 15, tzinfo=UTC)
        )
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            daily = write_report(snapshot, directory)
            self.assertEqual(daily.name, "qualite-2026-11-12.md")
            self.assertEqual(len(list(directory.glob("*.md"))), 2)
            self.assertIn("franceinfo", daily.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
