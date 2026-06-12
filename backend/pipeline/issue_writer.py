"""Biến transcript tiếng Việt -> draft Jira issue tiếng Anh (JSON).

Ưu tiên Gemini -> OpenAI (GPT) -> Groq (llama) tuỳ key nào có.
"""
import json

import requests

import config

ISSUE_PROMPT = """You are a QA assistant for a Roblox game studio.
A Vietnamese QA tester described a bug verbally while playtesting. Below are
transcript(s) of what they said (possibly from 2 ASR engines - cross-reference
them to correct ASR mistakes).

Transcripts:
{transcripts}

Write a Jira bug report in English. Respond with ONLY valid JSON, no markdown fence:
{{
  "title": "concise bug title in English",
  "description": "What happened, expected vs actual behavior. Markdown allowed.",
  "repro_steps": ["step 1", "step 2"],
  "severity": "low | medium | high | critical",
  "transcript_summary_vi": "tóm tắt 1-2 câu tiếng Việt những gì QA nói"
}}
If the transcript is empty or has no bug info, set title to "NO_BUG_DETECTED"."""


def _parse_json(text: str) -> dict:
    """LLM đôi khi bọc JSON trong ```...``` - gỡ ra rồi parse."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _format_transcripts(transcripts: dict) -> str:
    parts = []
    for engine, text in transcripts.items():
        if text:
            parts.append(f"--- {engine} ---\n{text}")
    return "\n\n".join(parts) if parts else "(empty)"


def _call_gemini(prompt: str) -> str:
    from google import genai

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    response = client.models.generate_content(model=config.GEMINI_MODEL, contents=prompt)
    return response.text or ""


def _call_groq(prompt: str) -> str:
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_openai(prompt: str) -> str:
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
        json={
            "model": config.OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def write_issue(transcripts: dict) -> dict:
    if not (config.GEMINI_API_KEY or config.OPENAI_API_KEY or config.GROQ_API_KEY):
        return {
            "title": "",
            "description": "",
            "repro_steps": [],
            "severity": "",
            "transcript_summary_vi": "",
        }
    prompt = ISSUE_PROMPT.format(transcripts=_format_transcripts(transcripts))
    try:
        if config.GEMINI_API_KEY:
            raw = _call_gemini(prompt)
        elif config.OPENAI_API_KEY:
            raw = _call_openai(prompt)
        else:
            raw = _call_groq(prompt)
        issue = _parse_json(raw)
    except Exception as e:
        print(f"[issue_writer] LLM lỗi, trả issue rỗng: {e}")
        issue = {
            "title": "",
            "description": "",
            "repro_steps": [],
            "severity": "",
            "transcript_summary_vi": "",
        }
    return issue
