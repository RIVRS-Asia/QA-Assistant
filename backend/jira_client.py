"""Push issue to Jira. Default = MOCK MODE: writes issue to pushed_issues.json.

Fill in JIRA_* in .env to push for real (Jira Cloud REST API v3).
"""
import json
from datetime import datetime
from pathlib import Path

import requests

import config


def push_issue(session_dir: Path, draft: dict) -> dict:
    if config.JIRA_ENABLED:
        return _push_real(draft)
    return _push_mock(session_dir, draft)


def _push_mock(session_dir: Path, draft: dict) -> dict:
    """Mock: append issue to JSON file, return a fake key."""
    out_file = session_dir / "pushed_issues.json"
    pushed = json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else []
    fake_key = f"MOCK-{len(pushed) + 1}"
    pushed.append({
        "key": fake_key,
        "pushed_at": datetime.now().isoformat(),
        "issue": draft["issue"],
        "video_clip": draft.get("video_clip"),
        "screenshots": draft.get("screenshots", []),
    })
    out_file.write_text(json.dumps(pushed, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"key": fake_key, "mock": True}


def _push_real(draft: dict) -> dict:
    issue = draft["issue"]
    description = issue["description"]
    if issue.get("repro_steps"):
        steps = "\n".join(f"{n+1}. {s}" for n, s in enumerate(issue["repro_steps"]))
        description += f"\n\nSteps to reproduce:\n{steps}"

    resp = requests.post(
        f"{config.JIRA_BASE_URL}/rest/api/3/issue",
        auth=(config.JIRA_EMAIL, config.JIRA_API_TOKEN),
        json={
            "fields": {
                "project": {"key": config.JIRA_PROJECT_KEY},
                "issuetype": {"name": "Bug"},
                "summary": issue["title"],
                "description": {
                    "type": "doc", "version": 1,
                    "content": [{"type": "paragraph",
                                 "content": [{"type": "text", "text": description}]}],
                },
            }
        },
        timeout=30,
    )
    resp.raise_for_status()
    key = resp.json()["key"]
    return {"key": key, "url": f"{config.JIRA_BASE_URL}/browse/{key}", "mock": False}
