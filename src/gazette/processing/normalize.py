"""Normalisation pure des métadonnées RSS pour le TD 4.

Aucun accès disque ou PostgreSQL ; aucun rejet ni dédoublonnage.
Les JSON bruts ne sont jamais modifiés.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

MAX_EXCERPT_LENGTH = 500  # Plafond éditorial de la couche propre (modifiable).
_SUSPICIOUS_ENCODING = re.compile(r"(?:Ã[\u0080-\u00bf©¨ª«®°]|Â[\u00a0-\u00bf]|â€|\ufffd)")
_WHITESPACE = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    """Retire les balises et ignore le contenu de script/style."""

    _SEPARATORS = {
        "p",
        "div",
        "br",
        "li",
        "ul",
        "ol",
        "section",
        "article",
        "h1",
        "h2",
        "h3",
        "blockquote",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.ignored += 1
        if tag in self._SEPARATORS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.ignored:
            self.ignored -= 1
        if tag in self._SEPARATORS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)


def strip_html(value: str | None) -> str:
    """Extrait du texte des balises HTML (les entités sont décodées)."""
    parser = _TextExtractor()
    parser.feed(value or "")
    parser.close()
    return "".join(parser.parts)


def normalize_spaces(value: str | None) -> str:
    """Transforme espaces insécables, tabulations et retours ligne en espaces simples."""
    return _WHITESPACE.sub(" ", (value or "").replace("\u200b", "")).strip()


def has_broken_encoding(value: str | None) -> bool:
    """Repère les séquences suspectes ; ce signal n'est pas un rejet automatique."""
    return bool(_SUSPICIOUS_ENCODING.search(value or ""))


def repair_encoding(value: str | None) -> str:
    """Répare uniquement un cas latin-1/UTF-8 réversible et plus lisible.

    Si l'origine ne peut pas être identifiée de manière prudente, conserve le texte.
    """
    original = value or ""
    if not has_broken_encoding(original):
        return original
    try:
        candidate = original.encode("latin-1").decode("utf-8")
    except (UnicodeError, ValueError):
        return original
    if len(_SUSPICIOUS_ENCODING.findall(candidate)) < len(_SUSPICIOUS_ENCODING.findall(original)):
        return candidate
    return original


def normalize_text(value: str | None) -> str:
    """Nettoie texte HTML, entités, espaces et mojibake réparable."""
    repaired = repair_encoding(value)
    return normalize_spaces(html.unescape(strip_html(repaired)))


def normalize_excerpt(value: str | None, max_length: int = MAX_EXCERPT_LENGTH) -> str:
    """Nettoie et borne un résumé sans rompre une paire de caractères Unicode."""
    if max_length < 0:
        raise ValueError("max_length doit être positif ou nul")
    return normalize_text(value)[:max_length].rstrip()


def normalize_date(value: str | datetime | None) -> str | None:
    """Retourne une date ISO 8601 UTC ; None si absente ou invalide.

    Les dates sans fuseau sont présumées UTC (choix explicite pour le TD 4).
    """
    if value is None or value == "":
        return None
    try:
        dt = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        )
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat()
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def normalize_article(
    article: dict[str, Any], max_excerpt_length: int = MAX_EXCERPT_LENGTH
) -> dict[str, Any]:
    """Renvoie une copie normalisée sans toucher à l'article d'origine.

    Préserve id, source, lien, payload, rubriques brutes en dehors du nettoyage
    de présentation et ajoute des indicateurs utiles à la future règle R07.
    """
    result = dict(article)
    title = normalize_text(article.get("titre"))
    excerpt = normalize_excerpt(article.get("resume"), max_excerpt_length)
    raw_categories = article.get("rubrique") or []
    if isinstance(raw_categories, str):
        raw_categories = [raw_categories]
    categories = [normalize_text(c) for c in raw_categories]
    result.update(
        {
            "titre": title,
            "resume": excerpt,
            "rubrique": [c for c in categories if c],
            "publie_le": normalize_date(article.get("publie_le")),
            "recupere_le": normalize_date(article.get("recupere_le")),
            "normalisation": {
                "encodage_suspect": has_broken_encoding(title + " " + excerpt),
                "date_publication_invalide": bool(article.get("publie_le"))
                and normalize_date(article.get("publie_le")) is None,
                "date_recuperation_invalide": bool(article.get("recupere_le"))
                and normalize_date(article.get("recupere_le")) is None,
            },
        }
    )
    return result
