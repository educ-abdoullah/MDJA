"""Console de contrôle et de traçabilité du pipeline Gazette."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(os.environ.get("GAZETTE_ROOT", "/opt/airflow"))
TASKS = [
    "collect_rss",
    "process_quality",
    "generate_quality_report",
    "check_quality",
    "cluster_themes",
]


def title(number, name):
    print(f"\n{'=' * 78}\n{number} | {name}\n{'=' * 78}")


def dump(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def query(sql, params=()):
    with closing(psycopg2.connect(os.environ["GAZETTE_DATABASE_URL"], connect_timeout=10)) as conn:
        conn.set_session(readonly=True)
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]


def table(rows, columns):
    if not rows:
        print("(aucune ligne)")
        return
    for row in rows:
        print(" | ".join(f"{key}={row.get(key)}" for key in columns))


def pause(enabled, text="ENTREE : etape suivante | Ctrl+C : quitter : "):
    if enabled:
        input("\n" + text)


def run_airflow():
    title("EXECUTION", "Pipeline Airflow - execution des cinq taches")
    print("Traitement : collecte, nettoyage, rapport, controles et regroupement.")
    print("Les donnees sont actualisees. Les alertes de production restent actives.")
    print("Les echecs par source sont comptabilises independamment du statut global du DAG.")
    log_dir = ROOT / "data/verification"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"pipeline-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.log"
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(
            ["airflow", "dags", "test", "gazette_daily"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            for line in process.stdout:
                stream.write(line)
                stream.flush()
                if "[DAG TEST]" in line or "state=success, run_type=" in line:
                    print(line.rstrip())
                elif line.startswith('{"event":'):
                    try:
                        event = json.loads(line)
                        event.pop("themes", None)  # Les themes seront affiches ensuite, un par un.
                        dump(event)
                    except json.JSONDecodeError:
                        print(line.rstrip())
                elif any(word in line.lower() for word in ("traceback", "[error", "exception:")):
                    print(line.rstrip())
            code = process.wait()
        except KeyboardInterrupt:
            process.terminate()
            process.wait(timeout=15)
            raise
    print(f"Journal complet sur le poste : data/verification/{log.name}")
    if code:
        raise RuntimeError(f"Le DAG a echoue (code {code}). Consulter ce journal et Airflow.")
    print("STATUT : execution terminee avec succes.")


def inspect_run(run, interactive):
    run_id = str(run["id"])
    title("6/8", "Embeddings : fenetre, modele, cache et metriques")
    dump(run)
    pause(interactive)
    title("7/8", "Themes et articles associes")
    themes = query(
        "SELECT label,nom,taille,mots_cles FROM themes WHERE run_id=%s ORDER BY label", (run_id,)
    )
    table(themes, ["label", "taille", "nom"])

    def show_members(label):
        members = query(
            """SELECT a.label,r.snapshot->>'source' AS source,r.snapshot->>'titre' AS titre,
            r.snapshot->>'resume' AS resume,r.snapshot->>'lien' AS lien
            FROM articles_themes a JOIN run_articles r USING(run_id,article_brut_id)
            WHERE a.run_id=%s AND a.label IS NOT DISTINCT FROM %s ORDER BY a.article_brut_id""",
            (run_id, label),
        )
        dump(members)

    if interactive:
        while True:
            choice = input("\nNumero du theme, B=articles isoles, ENTREE=suite : ").strip()
            if not choice:
                break
            if choice.upper() == "B":
                show_members(None)
            elif choice.isdigit() and any(t["label"] == int(choice) for t in themes):
                show_members(int(choice))
            else:
                print("Selection invalide. Valeurs acceptees : label affiche, B ou ENTREE.")
    elif themes:
        show_members(themes[0]["label"])

    title("8/8", "Controles de tracabilite et artefacts")
    counts = query(
        """SELECT (SELECT count(*) FROM run_articles WHERE run_id=%s) AS instantanes,
        (SELECT count(*) FROM articles_themes WHERE run_id=%s) AS affectations,
        (SELECT count(*) FROM articles_themes WHERE run_id=%s AND label IS NULL) AS bruit,
        (SELECT coalesce(sum(taille),0) FROM themes WHERE run_id=%s) AS classes""",
        (run_id,) * 4,
    )[0]
    dump(counts)
    valid = (
        counts["instantanes"] == counts["affectations"] == run["input_count"]
        and counts["classes"] + counts["bruit"] == run["input_count"]
    )
    print(
        ("OK" if valid else "ECHEC") + " : articles = classes + isoles = affectations = instantanes"
    )
    folder = ROOT / "data/mlops" / run_id
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    artifact_valid = True
    for name, metadata in manifest["files"].items():
        path = folder / name
        if path.parent != folder:
            raise ValueError("Chemin artefact inattendu")
        with path.open("rb") as stream:
            correct = hashlib.file_digest(stream, "sha256").hexdigest() == metadata["sha256"]
        artifact_valid &= correct
        print(f"{'OK' if correct else 'ECHEC'} SHA-256 : {name}")
    vectors = np.load(folder / "vectors.npy", allow_pickle=False)
    print(f"Matrice des embeddings : {vectors.shape}, nombres finis : {np.isfinite(vectors).all()}")
    print("Extrait du premier vecteur :", vectors[0, :8].tolist() if len(vectors) else "(lot vide)")
    print("Sur le poste : data/mlops/" + run_id)
    if not valid or not artifact_valid:
        raise RuntimeError("Incoherence de tracabilite detectee")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--no-pause", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.read_only and args.run:
        parser.error("--read-only et --run sont incompatibles")
    interactive = not args.no_pause
    title("GAZETTE", "Console de controle du pipeline")
    print("Sources -> brut -> nettoyage -> controles -> vecteurs -> themes")
    print("Donnees : PostgreSQL, fichiers bruts et artefacts MLOps.")
    print("Horodatage UTC : " + datetime.now(UTC).isoformat(timespec="seconds"))
    launch = args.run
    if interactive and not args.read_only and not launch:
        choice = (
            input(
                "\n1 = Consulter les resultats (lecture seule)\n"
                "2 = Executer le pipeline et controler les resultats\nQ = Quitter\nSelection [1] : "
            )
            .strip()
            .upper()
        )
        if choice == "Q":
            return
        if choice not in ("", "1", "2"):
            raise ValueError("Choix attendu : 1, 2 ou Q")
        launch = choice == "2"
    print("MODE : " + ("NOUVELLE EXECUTION" if launch else "LECTURE SEULE"))
    title("1/8", "Catalogue et etat des sources")
    sources = query(
        "SELECT id,url_flux,actif,derniere_reussite,echecs_consecutifs,"
        "sommeil_depuis,derniere_erreur FROM sources ORDER BY id"
    )
    table(sources, ["id", "actif", "echecs_consecutifs", "sommeil_depuis", "derniere_erreur"])
    for source in sources:
        print(f"  {source['id']} -> {source['url_flux']}")
    print(f"Nombre de sources enregistrees : {len(sources)}")
    pause(interactive)
    if launch:
        run_airflow()
    title("2/8", "Donnees brutes et volumes par source")
    table(
        query(
            "SELECT source,count(*) AS articles FROM articles_bruts_index "
            "GROUP BY source ORDER BY source"
        ),
        ["source", "articles"],
    )
    rows = query("SELECT id,chemin FROM articles_bruts_index ORDER BY recupere_le DESC,id LIMIT 1")
    raw = None
    if rows:
        root = (ROOT / "articles_bruts").resolve()
        path = (root / rows[0]["chemin"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Chemin brut hors du repertoire autorise")
        raw = json.loads(path.read_text(encoding="utf-8"))
        print("Exemple de JSON brut :")
        dump(raw)
    pause(interactive)
    title("3/8", "Normalisation - comparaison avant / apres")
    if raw:
        from gazette.processing.normalize import normalize_article

        clean = normalize_article(raw)
        for key in ("titre", "resume", "publie_le"):
            print(f"\n{key} AVANT : {raw.get(key)}\n{key} APRES : {clean.get(key)}")
        print(
            "Conservation du brut : intact. Longueur maximale du resume normalise : 500 caracteres."
        )
    pause(interactive)
    title("4/8", "Articles propres, rejets et motifs")
    table(
        query(
            "SELECT (SELECT count(*) FROM articles_bruts_index) AS bruts,"
            "(SELECT count(*) FROM articles_propres) AS propres,"
            "(SELECT count(*) FROM rejets) AS rejets"
        ),
        ["bruts", "propres", "rejets"],
    )
    table(
        query("SELECT source,regle_id,motif FROM rejets ORDER BY source LIMIT 20"),
        ["source", "regle_id", "motif"],
    )
    pause(interactive)
    title("5/8", "Controles qualite et rapport du jour")
    from gazette.processing.quality_checks import run_checks

    # Lecture SQL seulement : aucun webhook transmis, aucune alerte de test.
    result = run_checks(os.environ["GAZETTE_DATABASE_URL"], webhook_url=None)
    dump(result)
    print("Rapports locaux :")
    report_paths = sorted((ROOT / "rapports").glob("qualite-*.md"))
    for path in report_paths[-4:]:
        print("  rapports/" + path.name)
    if report_paths:
        latest_report = max(report_paths, key=lambda path: path.stat().st_mtime_ns)
        print("\nContenu du dernier rapport : " + latest_report.name)
        print(latest_report.read_text(encoding="utf-8"))
    pause(interactive)
    runs = query("SELECT * FROM runs WHERE status='success' ORDER BY started_at DESC LIMIT 5")
    if not runs:
        raise RuntimeError("Aucun run MLOps reussi. Choisir le mode 2 apres demarrage de la stack.")
    print("Derniers runs reussis :")
    table(runs, ["id", "airflow_run_id", "input_count", "finished_at"])
    inspect_run(runs[0], interactive)
    title("BILAN", "Resultats du controle")
    print("Tracabilite des affectations et integrite des artefacts : OK")
    print("Controle qualite : " + result["statut"])
    print("Coherence editoriale : evaluation humaine distincte des controles techniques.")
    print("Perimetre : tables courantes et instantanes du run MLOps selectionne.")
    print("Les tables courantes restent susceptibles d'evoluer avec les collectes planifiees.")
    print("Interface Airflow : http://localhost:8081")
    print("Documentation : docs/verification-visuelle.md et docs/mlops.md")
    if result["alertes"]:
        raise RuntimeError("Des anomalies qualite sont presentes : voir la section 5.")
    pause(interactive, "ENTREE : fermer la session de controle : ")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nVerification interrompue. Les services Docker restent demarres.")
        sys.exit(130)
    except Exception as error:
        print(f"\nECHEC : {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
