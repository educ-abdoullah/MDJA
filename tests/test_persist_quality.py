"""Tests sans base : decisions, stabilité et séparation des médias."""

import unittest
from datetime import UTC, datetime

from gazette.processing.persist import content_hash, prepare_decisions


class TestQualityPersistencePreparation(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 12, 12, tzinfo=UTC)

    def item(self, id, source="lemonde", title="Une actualité", resume="Un résumé"):
        return dict(
            id=id,
            source=source,
            titre=title,
            resume=resume,
            lien=f"https://example.com/{id}",
            publie_le="2026-11-12T08:00:00+00:00",
            recupere_le="2026-11-12T10:00:00+00:00",
            rubrique=[],
        )

    def test_jeu_rejete(self):
        kept, rejected = prepare_decisions(
            [self.item("a", title="QUIZ. Les expressions")], now=self.now
        )
        self.assertEqual(len(kept), 0)
        self.assertEqual(rejected[0].rule_id, "R04_jeux_concours")

    def test_doublon_exact_meme_source(self):
        kept, rejected = prepare_decisions([self.item("a"), self.item("b")], now=self.now)
        self.assertEqual([a["id"] for a in kept], ["a"])
        self.assertEqual(rejected[0].rule_id, "R08_doublon_exact")

    def test_sources_distinctes_preservees(self):
        kept, rejected = prepare_decisions(
            [self.item("a"), self.item("b", source="liberation")], now=self.now
        )
        self.assertEqual((len(kept), len(rejected)), (2, 0))

    def test_titres_proches_preserves(self):
        kept, rejected = prepare_decisions(
            [self.item("a"), self.item("b", title="Une autre actualité")], now=self.now
        )
        self.assertEqual((len(kept), len(rejected)), (2, 0))

    def test_hash_stable(self):
        a = self.item("a")
        self.assertEqual(content_hash(a), content_hash(dict(a, id="autre")))


if __name__ == "__main__":
    unittest.main()
