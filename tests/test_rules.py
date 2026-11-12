"""Tests unitaires des règles strictes du TD 4 (aucune DB ni réseau)."""

import unittest
from datetime import UTC, datetime, timedelta

from gazette.processing.normalize import normalize_article
from gazette.processing.rules import evaluate_article, filter_articles

NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)


def article(title="Une actualité", summary="Information", source="lemonde", **changes):
    raw = {
        "id": "x1",
        "source": source,
        "titre": title,
        "resume": summary,
        "lien": "https://example.org/a",
        "publie_le": "2026-11-12T08:00:00+00:00",
        "recupere_le": NOW.isoformat(),
        "rubrique": [],
    }
    raw.update(changes)
    return normalize_article(raw)


class TestRules(unittest.TestCase):
    def assert_rule(self, item, rule):
        result = evaluate_article(item, now=NOW)
        self.assertFalse(result.accepted)
        self.assertEqual(result.rule_id, rule)

    def test_publicite_et_contre_exemple(self):
        self.assert_rule(article("Contenu partenaire — offre spéciale"), "R01_publi")
        self.assertTrue(
            evaluate_article(article("Les dépenses publicitaires augmentent"), now=NOW).accepted
        )

    def test_horoscope_et_contre_exemple(self):
        self.assert_rule(article("Horoscope du jour"), "R02_horoscope")
        self.assertTrue(
            evaluate_article(article("La popularité de l’astrologie recule"), now=NOW).accepted
        )

    def test_programme_tv_et_contre_exemple(self):
        self.assert_rule(article("Programme TV de ce soir"), "R03_programme_tv")
        self.assertTrue(evaluate_article(article("Un débat à la télévision"), now=NOW).accepted)

    def test_jeux_et_contre_exemple(self):
        self.assert_rule(article("QUIZ. Expressions et ponctuation"), "R04_jeux_concours")
        self.assertTrue(
            evaluate_article(article("Les jeux vidéo stimulent la recherche"), now=NOW).accepted
        )

    def test_titre_vide_et_contre_exemple(self):
        self.assert_rule(article(" <p> </p> "), "R05_titre_vide")
        self.assertTrue(evaluate_article(article("Une vraie information"), now=NOW).accepted)

    def test_date_future_et_tolerance(self):
        future = (NOW + timedelta(minutes=6)).isoformat()
        self.assert_rule(article("Titre", publie_le=future), "R06_date_future")
        self.assertTrue(
            evaluate_article(
                article("Titre", publie_le=(NOW + timedelta(minutes=4)).isoformat()), now=NOW
            ).accepted
        )
        self.assertTrue(evaluate_article(article("Titre", publie_le=None), now=NOW).accepted)

    def test_encodage_invalide_et_contre_exemple(self):
        self.assert_rule(article("Information avec caractere �"), "R07_encodage")
        self.assertTrue(evaluate_article(article("Actualité française"), now=NOW).accepted)

    def test_doublon_exact_meme_source(self):
        kept, rejects = filter_articles(
            [article("Titre A", "Même résumé"), article("Titre A", "Même résumé")], now=NOW
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(rejects[0].rule_id, "R08_doublon_exact")

    def test_pas_de_doublon_entre_sources(self):
        kept, rejected = filter_articles(
            [
                article("Titre A", "Même résumé", "lemonde"),
                article("Titre A", "Même résumé", "liberation"),
            ],
            now=NOW,
        )
        self.assertEqual((len(kept), len(rejected)), (2, 0))

    def test_titres_proches_conserves(self):
        kept, rejected = filter_articles(
            [article("Un titre court", "Résumé"), article("Un titre très court", "Résumé")], now=NOW
        )
        self.assertEqual((len(kept), len(rejected)), (2, 0))

    def test_resumes_differents_conserves(self):
        kept, rejected = filter_articles(
            [article("Même titre", "Texte A"), article("Même titre", "Texte B")], now=NOW
        )
        self.assertEqual((len(kept), len(rejected)), (2, 0))

    def test_titre_generique(self):
        self.assert_rule(article("Début de direct"), "R09_titre_generique")
        self.assertTrue(
            evaluate_article(article("Début de direct sur les élections"), now=NOW).accepted
        )

    def test_immutabilite(self):
        a = article("Un titre", "Résumé")
        original = dict(a)
        kept, _ = filter_articles([a], now=NOW)
        self.assertEqual(a, original)
        self.assertIsNot(kept[0], a)


if __name__ == "__main__":
    unittest.main()
