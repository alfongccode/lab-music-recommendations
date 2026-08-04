"""
Extrae embeddings de audio con m-a-p/MERT-v1-330M y los sube a Pinecone.

Uso:
    export PINECONE_API_KEY="..."
    python mert_to_pinecone.py --audio-dir ./musica --index music-mert

Requisitos:
    pip install "transformers<4.41" torch torchaudio nnAudio pinecone soundfile
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
from pathlib import Path

import torch
import torchaudio
from transformers import AutoModel, Wav2Vec2FeatureExtractor

MODEL_ID = "m-a-p/MERT-v1-330M"
EMBED_DIM = 1024  # tamaño del hidden state de MERT-v1-330M
N_LAYERS = 25  # 1 embedding layer + 24 capas transformer
AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus"}


# --------------------------------------------------------------------------- #
# Modelo
# --------------------------------------------------------------------------- #
def build_model(device: str):
    """Carga el feature extractor y el modelo. Ambos necesitan trust_remote_code."""
    processor = Wav2Vec2FeatureExtractor.from_pretrained(
        MODEL_ID, trust_remote_code=True
    )
    model = AutoModel.from_pretrained(MODEL_ID, trust_remote_code=True)
    model = model.to(device).eval()
    return processor, model


# --------------------------------------------------------------------------- #
# Audio
# --------------------------------------------------------------------------- #
def _decode_with_ffmpeg(path: Path, target_sr: int) -> torch.Tensor:
    """Fallback universal: mp3, m4a, aac, opus, wma... todo lo que lea FFmpeg."""
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ac",
        "1",
        "-ar",
        str(target_sr),
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    return torch.frombuffer(bytearray(proc.stdout), dtype=torch.float32)


def load_audio(path: Path, target_sr: int) -> torch.Tensor:
    """Devuelve una forma de onda mono a target_sr, sea cual sea el códec."""
    try:
        wav, sr = torchaudio.load(str(path))
        wav = wav.mean(dim=0)  # a mono
        if sr != target_sr:
            wav = torchaudio.functional.resample(wav, sr, target_sr)
        if wav.numel() == 0:
            raise RuntimeError("decodificación vacía")
        return wav
    except Exception:
        return _decode_with_ffmpeg(path, target_sr)


def load_and_chunk(path: Path, target_sr: int, chunk_s: float, overlap_s: float):
    """Carga el audio a mono/target_sr y lo trocea en ventanas solapadas."""
    wav = load_audio(path, target_sr)

    duration = wav.numel() / target_sr
    chunk = int(chunk_s * target_sr)
    hop = max(1, int((chunk_s - overlap_s) * target_sr))

    if wav.numel() < chunk:  # audio muy corto -> padding
        wav = torch.nn.functional.pad(wav, (0, chunk - wav.numel()))

    chunks = [wav[i : i + chunk] for i in range(0, wav.numel() - chunk + 1, hop)]
    return chunks, duration


@torch.inference_mode()
def embed_file(path: Path, processor, model, device: str, args):
    """Devuelve un único vector de 1024 dims (float32, normalizado) por archivo."""
    chunks, duration = load_and_chunk(
        path, args.sample_rate, args.chunk_seconds, args.overlap_seconds
    )

    per_chunk = []
    for i in range(0, len(chunks), args.batch_size):
        batch = [c.numpy() for c in chunks[i : i + args.batch_size]]
        inputs = processor(
            batch,
            sampling_rate=args.sample_rate,
            return_tensors="pt",
            padding=True,
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        out = model(**inputs, output_hidden_states=True)
        # tupla de 25 tensores [B, T, 1024]  ->  [25, B, T, 1024]
        hidden = torch.stack(out.hidden_states, dim=0)
        hidden = hidden[args.layers]  # selección de capas
        vec = hidden.mean(dim=(0, 2))  # media capas + tiempo -> [B, 1024]
        per_chunk.append(vec.float().cpu())

    emb = torch.cat(per_chunk, dim=0).mean(dim=0)  # media de todos los fragmentos
    emb = torch.nn.functional.normalize(emb, dim=0)  # L2 -> cosine == dot product
    return emb.tolist(), duration


# --------------------------------------------------------------------------- #
# Pinecone
# --------------------------------------------------------------------------- #
def get_index(args):
    from pinecone import Pinecone, ServerlessSpec

    api_key = os.environ.get("PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError("Falta la variable de entorno PINECONE_API_KEY")

    pc = Pinecone(api_key=api_key)
    if not pc.has_index(args.index):
        print(f"Creando índice '{args.index}' (dim={EMBED_DIM}, metric=cosine)...")
        pc.create_index(
            name=args.index,
            dimension=EMBED_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud=args.cloud, region=args.region),
        )
    return pc.Index(args.index)


def make_id(path: Path, root: Path) -> str:
    """ID ASCII, estable y legible (Pinecone no admite IDs con caracteres raros)."""
    rel = path.relative_to(root).as_posix()
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", path.stem).strip("-").lower()[:48]
    digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:10]
    return f"{slug or 'track'}-{digest}"


def upsert_batches(index, vectors, namespace: str, size: int = 100):
    for i in range(0, len(vectors), size):
        index.upsert(vectors=vectors[i : i + size], namespace=namespace)
        print(f"  subidos {min(i + size, len(vectors))}/{len(vectors)}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_layers(spec: str):
    if spec == "all":
        return list(range(N_LAYERS))
    if spec == "last":
        return [N_LAYERS - 1]
    if spec == "middle":  # las capas medias suelen funcionar mejor en tagging
        return list(range(8, 17))
    return [int(x) for x in spec.split(",")]


def main():
    p = argparse.ArgumentParser(description="Embeddings MERT-v1-330M -> Pinecone")
    p.add_argument("--audio-dir", type=Path, required=True)
    p.add_argument("--index", default="music-mert")
    p.add_argument("--namespace", default="")
    p.add_argument("--cloud", default="aws")
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--chunk-seconds", type=float, default=10.0)
    p.add_argument("--overlap-seconds", type=float, default=0.0)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument(
        "--sample-rate", type=int, default=24000, help="MERT-v1 trabaja a 24 kHz"
    )
    p.add_argument(
        "--layers", default="middle", help="'all' | 'last' | 'middle' | '10,11,12'"
    )
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    p.add_argument(
        "--dry-run", action="store_true", help="calcula embeddings sin subirlos"
    )
    args = p.parse_args()

    args.layers = parse_layers(args.layers)

    files = sorted(
        f for f in args.audio_dir.rglob("*") if f.suffix.lower() in AUDIO_EXTS
    )
    if not files:
        raise SystemExit(f"No se encontró audio en {args.audio_dir}")
    print(f"{len(files)} archivos encontrados. Dispositivo: {args.device}")

    processor, model = build_model(args.device)
    # el processor conoce el sample rate esperado por el modelo
    args.sample_rate = getattr(processor, "sampling_rate", args.sample_rate)

    vectors = []
    for n, path in enumerate(files, 1):
        try:
            values, duration = embed_file(path, processor, model, args.device, args)
        except Exception as exc:  # archivo corrupto, códec, etc.
            print(f"[{n}/{len(files)}] ERROR {path.name}: {exc}")
            continue

        vectors.append(
            {
                "id": make_id(path, args.audio_dir),
                "values": values,
                "metadata": {
                    "filename": path.name,
                    "path": path.relative_to(args.audio_dir).as_posix(),
                    "duration_s": round(duration, 2),
                    "model": MODEL_ID,
                },
            }
        )
        print(f"[{n}/{len(files)}] {path.name} ({duration:.1f}s) OK")

    if args.dry_run:
        print(f"\nDry-run: {len(vectors)} embeddings calculados, nada subido.")
        return

    index = get_index(args)
    upsert_batches(index, vectors, args.namespace)
    print("\nEstadísticas del índice:", index.describe_index_stats())


if __name__ == "__main__":
    main()
