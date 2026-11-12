-- Historique indépendant des décisions de nettoyage courantes.
CREATE TABLE runs (
    id UUID PRIMARY KEY,
    airflow_run_id TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running','success','failed')),
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    input_hash CHAR(64),
    model TEXT NOT NULL,
    model_revision TEXT NOT NULL,
    parameters JSONB NOT NULL,
    software JSONB NOT NULL,
    metrics JSONB,
    artifacts JSONB,
    error TEXT
);
CREATE UNIQUE INDEX runs_airflow_success ON runs(airflow_run_id)
    WHERE status='success' AND airflow_run_id IS NOT NULL;

CREATE TABLE embeddings (
    cache_key CHAR(64) PRIMARY KEY,
    text_hash CHAR(64) NOT NULL,
    model TEXT NOT NULL,
    model_revision TEXT NOT NULL,
    preprocessing TEXT NOT NULL,
    dimension INTEGER NOT NULL CHECK (dimension > 0),
    vector JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE run_articles (
    run_id UUID NOT NULL REFERENCES runs(id),
    article_brut_id CHAR(64) NOT NULL REFERENCES articles_bruts_index(id),
    snapshot JSONB NOT NULL,
    text_hash CHAR(64) NOT NULL,
    PRIMARY KEY(run_id,article_brut_id)
);
CREATE TABLE themes (
    run_id UUID NOT NULL REFERENCES runs(id),
    label INTEGER NOT NULL CHECK (label >= 0),
    nom TEXT NOT NULL,
    mots_cles JSONB NOT NULL,
    taille INTEGER NOT NULL CHECK (taille > 0),
    PRIMARY KEY(run_id,label)
);
CREATE TABLE articles_themes (
    run_id UUID NOT NULL,
    article_brut_id CHAR(64) NOT NULL,
    label INTEGER,
    PRIMARY KEY(run_id,article_brut_id),
    FOREIGN KEY(run_id,article_brut_id) REFERENCES run_articles(run_id,article_brut_id),
    FOREIGN KEY(run_id,label) REFERENCES themes(run_id,label)
);
-- label NULL = bruit ; l'article et son instantané restent tracés.
