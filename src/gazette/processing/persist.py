"""TD 4 étape 4 : reconstruire la décision qualité depuis l'index des JSON bruts.

Exécution manuelle idempotente pour le volume actuel (petit) ; aucun JSON brut modifié.
La transaction garantit que les deux tables sont mises à jour ensemble.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gazette.processing.normalize import normalize_article
from gazette.processing.rules import filter_articles


def content_hash(article: dict[str, Any]) -> str:
    """Empreinte des champs normalisés (source séparée dans la clé SQL)."""
    content = json.dumps(
        [article["titre"].casefold(), article["resume"].casefold()],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def prepare_decisions(raw_articles: list[dict[str, Any]], *, now: datetime | None = None):
    """Nettoyer puis classer ; l'ordre stable de raw_articles choisit le premier doublon."""
    normalized = [normalize_article(a) for a in raw_articles]
    return filter_articles(normalized, now=now)


def read_indexed_raw(connection, raw_dir: Path) -> list[dict[str, Any]]:
    """Lire tous les JSON indexés, sans parcourir des fichiers hors de l'index."""
    root = raw_dir.resolve()
    articles = []
    with connection.cursor() as cursor:
        cursor.execute("""SELECT id, source, lien, chemin FROM articles_bruts_index
                          ORDER BY recupere_le ASC, id ASC""")
        rows = cursor.fetchall()
    for article_id, source, link, relative in rows:
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Chemin hors du stockage brut : {relative}")
        with path.open(encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict) or (data.get("id"), data.get("source"), data.get("lien")) != (
            article_id.strip(),
            source,
            link,
        ):
            raise ValueError(f"Index et JSON incohérents : {relative}")
        articles.append(data)
    return articles


def rebuild_quality(database_url: str, raw_dir: Path, *, now: datetime | None = None) -> dict:
    """Recalcul complet, sûr pour les relances. N'affecte pas les tables de collecte.

    Adapté à un premier TD et à quelques centaines d'items ; à rendre incrémental
    avant de traiter de très grands volumes. Ne pas l'exécuter concurremment
    avec un autre processus qualité ou une collecte sur la même base.
    """
    import psycopg2

    if now is None:
        now = datetime.now(UTC)
    with closing(psycopg2.connect(database_url, connect_timeout=10)) as conn:
        try:
            # L'acquisition du verrou précède la lecture pour sérialiser les recalculs.
            with conn.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext('gazette-qualite-rebuild'))")
            raw = read_indexed_raw(conn, raw_dir)
            kept, rejected = prepare_decisions(raw, now=now)
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM rejets")
                cursor.execute("DELETE FROM articles_propres")
                for article in kept:
                    cursor.execute(
                        """INSERT INTO articles_propres
                        (article_brut_id, source, empreinte_contenu, titre, resume, lien,
                         publie_le, recupere_le, rubrique)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                        (
                            article["id"],
                            article["source"],
                            content_hash(article),
                            article["titre"],
                            article["resume"],
                            article["lien"],
                            article["publie_le"],
                            article["recupere_le"],
                            json.dumps(article.get("rubrique") or [], ensure_ascii=False),
                        ),
                    )
                for decision in rejected:
                    article = decision.article
                    cursor.execute(
                        """INSERT INTO rejets
                        (article_brut_id, source, regle_id, motif)
                        VALUES (%s,%s,%s,%s)""",
                        (article["id"], article["source"], decision.rule_id, decision.reason),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "total": len(raw),
        "conserves": len(kept),
        "rejetes": len(rejected),
        "par_regle": dict(sorted(Counter(d.rule_id for d in rejected).items())),
    }


if __name__ == "__main__":
    result = rebuild_quality(
        os.environ["GAZETTE_DATABASE_URL"],
        Path(os.environ.get("GAZETTE_RAW_DIR", "articles_bruts")),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
