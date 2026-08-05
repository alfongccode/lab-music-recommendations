import os
import io
import torch
import torchaudio
import soundfile as sf
from pinecone import Pinecone
from transformers import AutoModel, Wav2Vec2FeatureExtractor

MODEL_ID = "m-a-p/MERT-v1-330M"
SAMPLE_RATE_MERT = 24000
CHUNK_SECONDS = 10.0
OVERLAP_SECONDS = 0.0
BATCH_SIZE = 1
PINECONE_INDEX_NAME = "music-recomendations"
PINECONE_NAMESPACE = "tiny-audios"

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
processor = Wav2Vec2FeatureExtractor.from_pretrained(MODEL_ID, trust_remote_code=True)
model = AutoModel.from_pretrained(MODEL_ID, trust_remote_code=True)

if torch.cuda.is_available():
  model = model.to(device).eval()

def chunk_audio_file(wav, audio_sample_rate):
  if audio_sample_rate != SAMPLE_RATE_MERT:
    wav = torchaudio.functional.resample(wav, audio_sample_rate, SAMPLE_RATE_MERT)

  chunk = int(CHUNK_SECONDS * SAMPLE_RATE_MERT)
  hop = max(1, int((CHUNK_SECONDS - OVERLAP_SECONDS) * SAMPLE_RATE_MERT))

  # Add padding on short audios
  if wav.numel() < chunk:
    wav = torch.nn.functional.pad(wav, (0, chunk - wav.numel()))

  # Chunk audio parts
  return [wav[i : i + chunk] for i in range(0, wav.numel() - chunk + 1, hop)]
    
def audio_embeddings(chunks):
  per_chunk = []

  for j in range(0, len(chunks), BATCH_SIZE):
      batch = [c.numpy() for c in chunks[j : j + BATCH_SIZE]]
      inputs = processor(
          batch,
          sampling_rate=SAMPLE_RATE_MERT,
          return_tensors="pt",
          padding=True,
      )
      inputs = {k: v.to(device) for k, v in inputs.items()}

      # inference_mode: no autograd graph, no retained activations
      # autocast: fp16 conv + attention, roughly halves activation memory
      with torch.inference_mode():
        with torch.autocast("cuda", dtype=torch.float16, enabled=device.type == "cuda"):
          out = model(**inputs, output_hidden_states=True)

          # index the tuple directly -- do NOT torch.stack all 25 layers
          hidden = out.hidden_states[12]   # (batch, frames, 1024)
          vec = hidden.mean(dim=1)                   # (batch, 1024)

      per_chunk.append(vec.float().cpu())
      del out, hidden, vec, inputs

  emb = torch.cat(per_chunk, dim=0).mean(dim=0)
  return torch.nn.functional.normalize(emb, dim=0)

async def audio_track_similaries(audio_track):
  audio_bytes = await audio_track.read()
  data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
  wav = torch.from_numpy(data).T
  if wav.ndim == 1:
      wav = wav.unsqueeze(0)
  wav = wav.mean(dim=0)
  track_chunks = chunk_audio_file(wav, audio_sample_rate=sr)
  track_emb = audio_embeddings(track_chunks)

  response = pc.Index(PINECONE_INDEX_NAME).query(
      vector=track_emb.tolist(),
      top_k=3,
      namespace=PINECONE_NAMESPACE,
      include_metadata=True,
  )
  print(response["matches"])
  return [ { "filename": match.metadata.get("path", ""), "score": match.score } for match in response["matches"] if match.metadata.get("filename", "") != getattr(audio_track, "filename", "") ]