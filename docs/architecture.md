
# Architecture — Gazette MDJA

## Schéma d'architecture

```mermaid

%%{init: {"theme": "base", "themeVariables": {"background": "#000000", "mainBkg": "#000000", "primaryTextColor": "#FFFFFF", "lineColor": "#94A3B8", "clusterBkg": "#000000", "clusterBorder": "#475569", "edgeLabelBackground": "#000000"}, "flowchart": {"curve": "linear", "nodeSpacing": 40, "rankSpacing": 55}}}%%
flowchart TB

    subgraph ARCH["ARCHITECTURE GAZETTE MDJA"]
        direction LR

        subgraph COL1["COLLECTE ET TRAITEMENT"]
            direction TB
            A[/"Presse nationale et régionale"/]
            B{"RSS disponible ?"}
            C["Flux RSS"]
            D["Scraping de secours"]
            E["Pipeline Python"]
            F["Nettoyage et normalisation"]
            G["Déduplication"]

            A --> B
            B -->|Oui| C
            B -->|Non| D
            C --> E
            D --> E
            E --> F
            F --> G
        end

        subgraph COL2["STOCKAGE ET EXPLOITATION"]
            direction TB
            H[("PostgreSQL")]
            I[("Archives brutes")]
            J{{"Contrôle des publications"}}
            K[["Logs Python structurés"]]
            L(["Gazette MDJA"])

            H --> J
            J --> K
            J --> L
        end

        G --> H
        E --> I
    end

    T(["Apache Airflow 3 : DAG quotidien"]) -.-> E
    DC[["Docker Compose"]] -.-> E
    V[["Git : code et configuration"]] -.-> DC

    classDef source fill:#172554,stroke:#60A5FA,stroke-width:2px,color:#DBEAFE
    classDef decision fill:#422006,stroke:#FBBF24,stroke-width:2px,color:#FEF3C7
    classDef process fill:#052E16,stroke:#4ADE80,stroke-width:2px,color:#DCFCE7
    classDef storage fill:#431407,stroke:#FB923C,stroke-width:2px,color:#FFEDD5
    classDef monitor fill:#450A0A,stroke:#F87171,stroke-width:2px,color:#FEE2E2
    classDef infra fill:#2E1065,stroke:#C084FC,stroke-width:2px,color:#F3E8FF
    classDef result fill:#042F2E,stroke:#2DD4BF,stroke-width:2px,color:#CCFBF1

    class A,C,D source
    class B decision
    class E,F,G process
    class H,I storage
    class J,K monitor
    class T,DC,V infra
    class L result

    style ARCH fill:#000000,stroke:#64748B,stroke-width:2px,color:#FFFFFF
    style COL1 fill:#000000,stroke:#475569,stroke-width:1px,color:#FFFFFF
    style COL2 fill:#000000,stroke:#475569,stroke-width:1px,color:#FFFFFF

    linkStyle default stroke:#94A3B8,stroke-width:2px,color:#FFFFFF

```

## État du prototype Airflow

Le schéma ci-dessus représente la cible métier. Le premier palier implémente uniquement
la collecte RSS et les archives JSON. Le scraping de secours, le stockage métier, le
regroupement et la publication ne sont pas encore implémentés.

```mermaid
flowchart LR
    C[Docker Compose] --> A[API Airflow : localhost 8081]
    C --> S[Scheduler : LocalExecutor]
    C --> D[Processeur de DAG]
    C --> P[(PostgreSQL : métadonnées Airflow)]
    D --> P
    S --> P
    A --> P
    S --> R[Collecte RSS par source]
    R --> J[Archives JSON et logs persistants]
```

Le DAG est programmé à 6 h Europe/Paris et créé en pause. Aucun service de publication
n'est encore actif. Les archives sont propres à chaque run et remplaçables lors d'un retry.
