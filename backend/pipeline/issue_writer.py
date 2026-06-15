"""Convert Vietnamese transcript -> draft Jira issue in English (JSON).

Priority: Gemini -> OpenAI (GPT) -> Groq (llama), whichever key is available.
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

Write a Jira bug report in English following the studio's bug template. Respond with
ONLY valid JSON, no markdown fence:
{{
  "title": "concise bug title in English",
  "repro_steps": ["step 1", "step 2"],
  "actual_result": "what actually happens (the bug)",
  "expected_result": "what should happen instead",
  "priority": "Low | Medium | High",
  "labels": ["optional UPPER_SNAKE_CASE tags, e.g. MUST_FIX; [] if none"],
  "transcript_summary_vi": "tóm tắt 1-2 câu tiếng Việt những gì QA nói"
}}
If the transcript is empty or has no bug info, set title to "NO_BUG_DETECTED"."""

EMPTY_ISSUE = {
    "title": "",
    "repro_steps": [],
    "actual_result": "",
    "expected_result": "",
    "priority": "Medium",
    "labels": [],
    "transcript_summary_vi": "",
}


def _parse_json(text: str) -> dict:
    """LLM sometimes wraps JSON in ```...``` - strip it out before parsing."""
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


def _clean_transcript_text(text: str | None) -> str:
    """Skip engine error markers like '[gemini error: ...]' and blank values."""
    text = (text or "").strip()
    if not text or text.startswith("["):
        return ""
    return text


def _fallback_title(transcripts: dict, issue: dict) -> str:
    """When the LLM gives no usable title, derive one from what the QA said so the web
    title field is still auto-filled (transcript-only, no vision). Returns "" only when
    there is genuinely nothing to summarise."""
    summary = (issue.get("transcript_summary_vi") or "").strip()
    if summary:
        return _shorten(summary)
    for engine in ("gemini", "openai", "groq"):
        text = _clean_transcript_text(transcripts.get(engine))
        if text:
            first = text.replace("\n", " ").strip().split(". ")[0]
            return _shorten(first)
    return ""


def _shorten(text: str, limit: int = 80) -> str:
    text = text.strip().rstrip(".")
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


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
        return dict(EMPTY_ISSUE)
    prompt = ISSUE_PROMPT.format(transcripts=_format_transcripts(transcripts))
    try:
        if config.GEMINI_API_KEY:
            raw = _call_gemini(prompt)
        elif config.OPENAI_API_KEY:
            raw = _call_openai(prompt)
        else:
            raw = _call_groq(prompt)
        issue = {**EMPTY_ISSUE, **_parse_json(raw)}
    except Exception as e:
        print(f"[issue_writer] LLM error, returning empty issue: {e}")
        issue = dict(EMPTY_ISSUE)

    # Always auto-fill a title for the web from the transcript when the LLM gave none
    # (empty, or its "no bug" sentinel). Stays empty only if the QA said nothing usable.
    title = (issue.get("title") or "").strip()
    if not title or title == "NO_BUG_DETECTED":
        issue["title"] = _fallback_title(transcripts, issue)
    return issue
