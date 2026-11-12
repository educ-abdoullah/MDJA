"""Règles éditoriales explicites du TD 4, sans effet de bord.

Les entrées doivent avoir été normalisées par ``normalize_article``.
La première règle correspondante est conservée comme motif principal.
Les doublons ne sont comparés QU'À L'INTÉRIEUR d'une même source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

from .normalize import has_broken_encoding

FUTURE_TOLERANCE = timedelta(minutes=5)

# Motifs volontairement stricts : on ne rejette jamais sur le mot « jeu » seul.
_PROMO = re.compile(
    (
        r"\b(?:contenu\s+partenaire|publi[ -]?reportage|"
        r"article\s+sponsoris[ée]|contenu\s+sponsoris[ée]|communiqu[ée]\s+commercial)\b"
    ),
    re.I,
)
_HOROSCOPE = re.compile(r"\bhoroscope\b", re.I)
_TV = re.compile(r"\b(?:programme[s]?\s+(?:tv|t[ée]l[ée])|grille\s+(?:tv|t[ée]l[ée]))\b", re.I)
_GAMES = re.compile(
    (
        r"\b(?:quiz|quizz|sudoku|mots[ -]crois[ée]s|mots[ -]fl[ée]ch[ée]s|"
        r"jeu[ -]concours|jeux[ -]concours|participez\s+[àa]\s+notre\s+concours)\b"
    ),
    re.I,
)
_GENERIC = {"début de direct"}


@dataclass(frozen=True)
class Decision:
    """Décision lisible et traçable ; article est une copie indépendante."""

    accepted: bool
    article: dict[str, Any]
    rule_id: str | None = None
    reason: str | None = None


def _text(article: dict[str, Any]) -> tuple[str, list[str]]:
    title = str(article.get("titre") or "").strip()
    categories = article.get("rubrique") or []
    if isinstance(categories, str):
        categories = [categories]
    return title, [str(c).strip() for c in categories]


def _future_date(article: dict[str, Any], now: datetime) -> bool:
    raw = article.get("publie_le")
    if not raw:
        return False  # Une date absente n'est pas une date future.
    try:
        date = (
            raw
            if isinstance(raw, datetime)
            else datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        )
        if date.tzinfo is None:
            return False  # A normaliser en amont ; éviter un rejet injustifié.
        return date.astimezone(UTC) > now.astimezone(UTC) + FUTURE_TOLERANCE
    except (ValueError, TypeError, OverflowError):
        return False


def _broken(article: dict[str, Any]) -> bool:
    title, _ = _text(article)
    excerpt = str(article.get("resume") or "")
    flags = article.get("normalisation") or {}
    return bool(flags.get("encodage_suspect")) or has_broken_encoding(title + " " + excerpt)


def evaluate_article(
    article: dict[str, Any],
    *,
    now: datetime | None = None,
    seen: set[tuple[str, str, str]] | None = None,
) -> Decision:
    """Évalue un article *déjà normalisé*, sans changer seen ni l'article.

    Si ``seen`` est fourni, R08 s'applique aux articles déjà ACCEPTÉS. Pour gérer
    les doublons d'un lot, préférer ``filter_articles`` qui gère cet état.
    """
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now doit contenir un fuseau horaire")
    title, categories = _text(article)
    normalized_title = title.casefold()
    # Les rubriques doivent être explicites ; « télé » seul pourrait désigner une actualité.
    source = str(article.get("source") or "")
    excerpt = str(article.get("resume") or "").strip()
    key = (source, normalized_title, excerpt.casefold())

    reason: tuple[str, str] | None = None
    if _PROMO.search(title) or any(_PROMO.search(cat) for cat in categories):
        reason = ("R01_publi", "Mention explicite de contenu publicitaire")
    elif _HOROSCOPE.search(title) or any(_HOROSCOPE.fullmatch(cat) for cat in categories):
        reason = ("R02_horoscope", "Horoscope")
    elif _TV.search(title) or any(_TV.fullmatch(cat) for cat in categories):
        reason = ("R03_programme_tv", "Grille ou programme TV")
    elif _GAMES.search(title) or any(_GAMES.search(cat) for cat in categories):
        reason = ("R04_jeux_concours", "Quiz, jeu ou concours")
    elif not title:
        reason = ("R05_titre_vide", "Titre vide après normalisation")
    elif _future_date(article, now):
        reason = ("R06_date_future", "Date de publication dans le futur (tolérance 5 min)")
    elif _broken(article):
        reason = ("R07_encodage", "Encodage suspect persistant après normalisation")
    elif seen is not None and key in seen:
        reason = ("R08_doublon_exact", "Même source, même titre et même résumé normalisés")
    elif normalized_title in _GENERIC:
        reason = ("R09_titre_generique", "Titre générique non informatif")

    return Decision(
        accepted=reason is None,
        article=dict(article),
        rule_id=reason[0] if reason else None,
        reason=reason[1] if reason else None,
    )


def filter_articles(
    articles: Iterable[dict[str, Any]], *, now: datetime | None = None
) -> tuple[list[dict[str, Any]], list[Decision]]:
    """Renvoie (articles conservés, rejets), sans supprimer les articles bruts.

    L'ordre d'entrée détermine la version conservée parmi les doublons parfaits.
    Pour rendre le résultat stable, fournir une liste triée (p.ex. par ID brut).
    Les réexécutions en base devront aussi consulter les articles déjà conservés.
    """
    now = now or datetime.now(UTC)
    seen: set[tuple[str, str, str]] = set()
    kept: list[dict[str, Any]] = []
    rejected: list[Decision] = []
    for article in articles:
        decision = evaluate_article(article, now=now, seen=seen)
        if decision.accepted and any(near_duplicate(article, prior) for prior in kept):
            decision = Decision(
                False,
                dict(article),
                "R10_doublon_approximatif",
                "Même source : titres proches et résumés similaires (Jaccard)",
            )
        if decision.accepted:
            title, _ = _text(article)
            seen.add(
                (
                    str(article.get("source") or ""),
                    title.casefold(),
                    str(article.get("resume") or "").strip().casefold(),
                )
            )
            kept.append(decision.article)
        else:
            rejected.append(decision)
    return kept, rejected


def near_duplicate(article: dict[str, Any], prior: dict[str, Any]) -> bool:
    """Comparaison prudente intra-source : titre >= 6 mots, Jaccard >= 0,85/0,90."""
    if article.get("source") != prior.get("source"):
        return False

    def words(value):
        return set(re.findall(r"\w+", str(value or "").casefold()))

    title, other_title = words(article.get("titre")), words(prior.get("titre"))
    summary, other_summary = words(article.get("resume")), words(prior.get("resume"))
    if min(len(title), len(other_title)) < 6 or not summary or not other_summary:
        return False
    return (
        len(title & other_title) / len(title | other_title) >= 0.85
        and len(summary & other_summary) / len(summary | other_summary) >= 0.90
    )
