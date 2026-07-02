"""Vietnamese/English transcription - runs 2 engines in parallel for comparison:

1. Gemini Flash: multimodal LLM, understands context so it handles regional accents +
   game terminology better.
2. Groq Whisper large-v3: cheap, fast, baseline for cross-reference.

Any engine without an API key is skipped.
"""
from pathlib import Path

import requests

import config

TRANSCRIBE_PROMPT = (
    "This is an audio recording of a Vietnamese or English QA tester (may speak Northern/Central/Southern accent) "
    "describing a bug while playtesting a Roblox game. "
    "Transcribe EXACTLY what this person said in Vietnamese or English. "
    "Keep game/English terminology as-is (e.g. spawn, lag, NPC, respawn). "
    "Return only the transcript content, no additional explanation. "
    "If the audio contains no speech (silence, breathing, or game sounds only), return an empty response - "
    "do NOT invent words that were not clearly spoken."
)


def transcribe_gemini(audio_path: Path) -> str | None:
    if not config.GEMINI_API_KEY:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=config.GEMINI_API_KEY)
        audio_bytes = audio_path.read_bytes()
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[
                TRANSCRIBE_PROMPT,
                types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
            ],
        )
        return (response.text or "").strip()
    except Exception as e:
        return f"[gemini error: {e}]"


def transcribe_groq(audio_path: Path) -> str | None:
    if not config.GROQ_API_KEY:
        return None
    try:
        with open(audio_path, "rb") as f:
            resp = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                files={"file": (audio_path.name, f, "audio/wav")},
                data={"model": config.GROQ_WHISPER_MODEL, "language": "vi"},
                timeout=120,
            )
        resp.raise_for_status()
        return resp.json().get("text", "").strip()
    except Exception as e:
        return f"[groq error: {e}]"


def transcribe_openai(audio_path: Path) -> str | None:
    if not config.OPENAI_API_KEY:
        return None
    try:
        with open(audio_path, "rb") as f:
            resp = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                files={"file": (audio_path.name, f, "audio/wav")},
                data={"model": config.OPENAI_WHISPER_MODEL, "language": "vi"},
                timeout=120,
            )
        resp.raise_for_status()
        return resp.json().get("text", "").strip()
    except Exception as e:
        return f"[openai error: {e}]"


def transcribe_all(audio_path: Path) -> dict:
    """Returns {'gemini': ..., 'groq': ..., 'openai': ...} - None if an engine has no key."""
    return {
        "gemini": transcribe_gemini(audio_path),
        "groq": transcribe_groq(audio_path),
        "openai": transcribe_openai(audio_path),
    }
