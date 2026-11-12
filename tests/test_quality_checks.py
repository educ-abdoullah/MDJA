import unittest
from unittest.mock import MagicMock, patch

from gazette.processing.quality_checks import (
    evaluate_quality,
    make_webhook_payload,
    read_integrity_counts,
    send_webhook,
)


def snapshot(rate=10, pending=0):
    return {
        "totaux": {"entres": 10, "gardes": 9 - pending, "rejetes": 1, "non_classes": pending},
        "par_source": [
            {
                "source": "lemonde",
                "entres": 10,
                "gardes": 9 - pending,
                "rejetes": 1,
                "taux_rejet_pct": rate,
                "non_classes": pending,
            }
        ],
        "par_regle": {"R04_jeux_concours": 1},
    }


class QualityTests(unittest.TestCase):
    def test_healthy(self):
        result = evaluate_quality(snapshot(), {"titres_vides": 0, "dates_futures": 0})
        self.assertEqual(result["statut"], "OK")
        self.assertEqual(result["alertes"], [])

    def test_rejection_threshold_strictly_greater(self):
        self.assertEqual(evaluate_quality(snapshot(rate=80), {})["statut"], "OK")
        result = evaluate_quality(snapshot(rate=81), {})
        self.assertEqual(result["alertes"][0]["code"], "taux_rejet_excessif")

    def test_integrity_and_pending(self):
        result = evaluate_quality(snapshot(pending=2), {"titres_vides": 1})
        self.assertEqual(
            {x["code"] for x in result["alertes"]}, {"titres_vides", "articles_non_classes"}
        )

    def test_empty_source(self):
        snap = snapshot()
        snap["par_source"][0]["taux_rejet_pct"] = None
        self.assertEqual(evaluate_quality(snap, {})["statut"], "OK")

    def test_read_integrity_counts(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.side_effect = [(0,), (1,), (0,), (0,), (0,), (0,)]
        data = read_integrity_counts(conn)
        self.assertEqual(data["dates_futures"], 1)
        self.assertEqual(cur.execute.call_count, 6)

    def test_webhook_payloads(self):
        data = {"alertes": [{"description": "test"}]}
        self.assertIn("content", make_webhook_payload(data, "discord"))
        self.assertIn("text", make_webhook_payload(data, "slack"))

    def test_reject_insecure_webhook(self):
        with self.assertRaises(ValueError):
            send_webhook({"alertes": []}, "http://example.com/webhook", "discord")

    @patch("gazette.processing.quality_checks.urlopen")
    def test_send_webhook(self, mocked):
        data = {"alertes": [{"description": "test"}]}
        send_webhook(data, "https://discord.com/api/webhooks/123/token", "discord")
        mocked.assert_called_once()
        req = mocked.call_args.args[0]
        self.assertIn(b"content", req.data)


if __name__ == "__main__":
    unittest.main()
