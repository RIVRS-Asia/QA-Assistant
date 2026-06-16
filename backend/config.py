"""General configuration - read from .env file in the project root."""
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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_WHISPER_MODEL = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")

# OBS WebSocket
OBS_HOST = os.getenv("OBS_HOST", "localhost")
OBS_PORT = int(os.getenv("OBS_PORT", "4455"))
OBS_PASSWORD = os.getenv("OBS_PASSWORD", "")

# Recording / markers
RECORD_HOTKEY = os.getenv("RECORD_HOTKEY", "<ctrl>+<shift>+<f9>")    # NEW bug with video clip
CAPTURE_HOTKEY = os.getenv("CAPTURE_HOTKEY", "<ctrl>+<shift>+<f10>")  # NEW bug with screenshot
APPEND_HOTKEY = os.getenv("APPEND_HOTKEY", "<ctrl>+<shift>+<f11>")    # add another screenshot to the OPEN bug
MIC_AUDIO_STREAM = int(os.getenv("MIC_AUDIO_STREAM", "0"))

# Record clip = PRE seconds before + POST seconds after the press. OBS Max Replay Time must be >= PRE+POST.
# (POST = wait time after pressing before saving the replay buffer, because the buffer only holds the past.)
RECORD_PRE_SECONDS = float(os.getenv("RECORD_PRE_SECONDS", "20"))
RECORD_POST_SECONDS = float(os.getenv("RECORD_POST_SECONDS", "20"))

# Jira (empty = mock mode)
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "")

JIRA_ENABLED = bool(JIRA_BASE_URL and JIRA_API_TOKEN and JIRA_PROJECT_KEY)
