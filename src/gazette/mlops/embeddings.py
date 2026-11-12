"""MiniLM ONNX : tokenisation, mean pooling masqué, normalisation L2 et cache SQL."""

import hashlib
import json
import re

import numpy as np


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def article_text(article):
    return f"{article['titre'].strip()}\n{article['resume'].strip()}"


def cache_identity(text, config):
    return digest({"text_hash": digest(text), "embedding": config})


class OnnxEncoder:
    def __init__(self, config):
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        self.config = config
        paths = {
            name: hf_hub_download(config["model"], name, revision=config["revision"])
            for name in ("tokenizer.json", config["file"])
        }
        self.file_hashes = {}
        for name, path in paths.items():
            with open(path, "rb") as stream:
                self.file_hashes[name] = hashlib.file_digest(stream, "sha256").hexdigest()
        self.tokenizer = Tokenizer.from_file(paths["tokenizer.json"])
        self.tokenizer.enable_truncation(max_length=config["max_length"])
        self.tokenizer.enable_padding(pad_id=0, pad_token="<pad>")
        options = ort.SessionOptions()
        options.intra_op_num_threads = config["threads"]
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            paths[config["file"]], sess_options=options, providers=["CPUExecutionProvider"]
        )

    def encode(self, texts):
        outputs = []
        for start in range(0, len(texts), self.config["batch_size"]):
            batch = self.tokenizer.encode_batch(texts[start : start + self.config["batch_size"]])
            inputs = {
                "input_ids": np.array([x.ids for x in batch], dtype=np.int64),
                "attention_mask": np.array([x.attention_mask for x in batch], dtype=np.int64),
                "token_type_ids": np.array([x.type_ids for x in batch], dtype=np.int64),
            }
            hidden = self.session.run(
                None, {x.name: inputs[x.name] for x in self.session.get_inputs()}
            )[0]
            mask = inputs["attention_mask"][..., None]
            pooled = (hidden * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1)
            pooled /= np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
            outputs.extend(pooled.astype(np.float32))
        return np.asarray(outputs, dtype=np.float32)


def validate_vectors(vectors, count, dimension):
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.shape != (count, dimension) or not np.isfinite(vectors).all():
        raise ValueError("Embeddings : forme ou valeurs invalides")
    if count and not np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-4):
        raise ValueError("Embeddings non normalisés ou nuls")
    return vectors


def embed_cached(connection, articles, config, encoder_factory=OnnxEncoder):
    if not re.fullmatch(r"[a-f0-9]{40}", config["revision"]):
        raise ValueError("Une révision immuable du modèle est obligatoire")
    texts = [article_text(a) for a in articles]
    keys = [cache_identity(t, config) for t in texts]
    cached = {}
    if keys:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT cache_key,vector FROM embeddings WHERE cache_key=ANY(%s)", (keys,)
            )
            cached = {key.strip(): vector for key, vector in cursor.fetchall()}
    missing = dict.fromkeys(key for key in keys if key not in cached)
    model_files = {}
    if missing:
        encoder = encoder_factory(config)
        model_files = getattr(encoder, "file_hashes", {})
        unique_texts = {key: text for key, text in zip(keys, texts, strict=True)}
        vectors = validate_vectors(
            encoder.encode([unique_texts[k] for k in missing]), len(missing), config["dimension"]
        )
        with connection.cursor() as cursor:
            for key, vector in zip(missing, vectors, strict=True):
                cached[key] = vector.tolist()
                cursor.execute(
                    """INSERT INTO embeddings
                    (cache_key,text_hash,model,model_revision,preprocessing,dimension,vector)
                    VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING""",
                    (
                        key,
                        digest(unique_texts[key]),
                        config["model"],
                        config["revision"],
                        config["preprocessing"],
                        config["dimension"],
                        json.dumps(cached[key]),
                    ),
                )
        connection.commit()
    vectors = np.array([cached[k] for k in keys], dtype=np.float32).reshape(
        len(keys), config["dimension"]
    )
    return validate_vectors(vectors, len(keys), config["dimension"]), {
        "cache_hits": len(keys) - sum(k in missing for k in keys),
        "encoded_texts": len(missing),
        "model_files_sha256": model_files,
    }
