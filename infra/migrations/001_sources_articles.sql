CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    nom TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    region TEXT NOT NULL DEFAULT '',
    url_flux TEXT NOT NULL UNIQUE,
    acces TEXT NOT NULL DEFAULT '',
    conditions TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    actif BOOLEAN NOT NULL DEFAULT TRUE,
    derniere_reussite TIMESTAMPTZ,
    echecs_consecutifs INTEGER NOT NULL DEFAULT 0 CHECK (echecs_consecutifs >= 0),
    etag TEXT,
    last_modified TEXT,
    sommeil_depuis TIMESTAMPTZ,
    derniere_erreur TEXT
);

CREATE TABLE articles_bruts_index (
    id CHAR(64) PRIMARY KEY,
    source TEXT NOT NULL REFERENCES sources(id),
    lien TEXT NOT NULL,
    chemin TEXT NOT NULL,
    recupere_le TIMESTAMPTZ NOT NULL,
    UNIQUE (source, lien)
);
