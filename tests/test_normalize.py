"""Tests unitaires purs de la normalisation du TD 4."""

import unittest
from datetime import datetime

from gazette.processing.normalize import (
    has_broken_encoding,
    normalize_article,
    normalize_date,
    normalize_excerpt,
    normalize_spaces,
    normalize_text,
    repair_encoding,
    strip_html,
)


class NormalizeTests(unittest.TestCase):
    def test_strip_html_and_entities(self):
        self.assertEqual(
            strip_html("<p>Bonjour&nbsp;<b>Paris</b></p><p>Suite</p>"), " Bonjour\xa0Paris  Suite "
        )

    def test_ignores_script(self):
        self.assertEqual(normalize_text("<p>Info</p><script>secret()</script>"), "Info")

    def test_normalize_spaces(self):
        self.assertEqual(normalize_spaces(" bon\u00a0  jour\n\tParis\u202f! "), "bon jour Paris !")

    def test_normalize_text(self):
        self.assertEqual(
            normalize_text("<p>L&#39;actualité&nbsp;du jour</p>"), "L'actualité du jour"
        )

    def test_repair_encoding(self):
        self.assertEqual(repair_encoding("ActualitÃ©"), "Actualité")
        self.assertEqual(repair_encoding("Actualité"), "Actualité")

    def test_unrepairable_encoding_flag(self):
        self.assertTrue(has_broken_encoding("Texte Ã© et �"))
        self.assertEqual(repair_encoding("Texte Ã© et �"), "Texte Ã© et �")

    def test_excerpt_limit(self):
        self.assertEqual(normalize_excerpt("<p>Bonjour&nbsp;monde !</p>", 7), "Bonjour")
        with self.assertRaises(ValueError):
            normalize_excerpt("a", -1)

    def test_date_utc(self):
        self.assertEqual(normalize_date("2026-11-12T10:30:00+01:00"), "2026-11-12T09:30:00+00:00")
        self.assertEqual(normalize_date("2026-11-12T09:30:00Z"), "2026-11-12T09:30:00+00:00")
        self.assertIsNone(normalize_date("n'importe quoi"))

    def test_date_naive_assumed_utc(self):
        self.assertEqual(normalize_date(datetime(2026, 11, 12, 9, 30)), "2026-11-12T09:30:00+00:00")

    def test_normalize_article_preserves_original(self):
        source = {
            "id": "abc",
            "source": "lemonde",
            "lien": "https://example.org/a",
            "titre": " <b>Bonjour&nbsp;Paris</b> ",
            "resume": "<p>Résumé</p>",
            "rubrique": ["&Eacute;conomie"],
            "publie_le": "invalide",
            "recupere_le": "2026-11-12T09:30:00Z",
            "payload": {"guid_ou_id": "1"},
        }
        result = normalize_article(source)
        self.assertEqual(result["titre"], "Bonjour Paris")
        self.assertEqual(result["rubrique"], ["Économie"])
        self.assertTrue(result["normalisation"]["date_publication_invalide"])
        self.assertEqual(result["id"], source["id"])
        self.assertEqual(result["payload"], source["payload"])
        self.assertIn("&nbsp;", source["titre"])

    def test_no_filtering_or_deduplication(self):
        a = {"source": "a", "titre": "Même titre", "resume": "Même résumé"}
        b = {"source": "b", "titre": "Même titre", "resume": "Même résumé"}
        self.assertEqual(normalize_article(a)["titre"], normalize_article(b)["titre"])


if __name__ == "__main__":
    unittest.main()
