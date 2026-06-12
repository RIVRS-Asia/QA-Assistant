"""Transcribe tiếng Việt - chạy song song 2 engine để so sánh:

1. Gemini Flash: multimodal LLM, hiểu ngữ cảnh nên nhận giọng vùng miền +
   thuật ngữ game tốt hơn.
2. Groq Whisper large-v3: rẻ, nhanh, baseline để đối chiếu.

Engine nào không có API key thì bỏ qua.
"""
from pathlib import Path

import requests

import config

TRANSCRIBE_PROMPT = (
    "Đây là đoạn ghi âm một QA tester người Việt (có thể nói giọng Bắc/Trung/Nam) "
    "đang mô tả lỗi (bug) khi chơi thử game Roblox. "
    "Hãy chép lại CHÍNH XÁC những gì người này nói bằng tiếng Việt. "
    "Giữ nguyên thuật ngữ game/tiếng Anh nếu có (ví dụ: spawn, lag, NPC, respawn). "
    "Chỉ trả về nội dung transcript, không giải thích thêm."
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
        return f"[gemini lỗi: {e}]"


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
        return f"[groq lỗi: {e}]"


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
        return f"[openai lỗi: {e}]"


def transcribe_all(audio_path: Path) -> dict:
    """Trả về {'gemini': ..., 'groq': ..., 'openai': ...} - None nếu engine không có key."""
    return {
        "gemini": transcribe_gemini(audio_path),
        "groq": transcribe_groq(audio_path),
        "openai": transcribe_openai(audio_path),
    }
