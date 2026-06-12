"""Cấu hình chung - đọc từ file .env ở thư mục gốc."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

SESSIONS_DIR = ROOT_DIR / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

# API keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")

# OBS WebSocket
OBS_HOST = os.getenv("OBS_HOST", "localhost")
OBS_PORT = int(os.getenv("OBS_PORT", "4455"))
OBS_PASSWORD = os.getenv("OBS_PASSWORD", "")

# Recording / markers
MARKER_HOTKEY = os.getenv("MARKER_HOTKEY", "<ctrl>+<shift>+<f9>")
MIC_AUDIO_STREAM = int(os.getenv("MIC_AUDIO_STREAM", "0"))

# Pipeline
CLIP_PRE_SECONDS = float(os.getenv("CLIP_PRE_SECONDS", "30"))
CLIP_POST_SECONDS = float(os.getenv("CLIP_POST_SECONDS", "10"))

# Jira (trống = mock mode)
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "")

JIRA_ENABLED = bool(JIRA_BASE_URL and JIRA_API_TOKEN and JIRA_PROJECT_KEY)
