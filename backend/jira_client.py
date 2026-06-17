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
        return _push_real(session_dir, draft)
    return _push_mock(session_dir, draft)


def _adf_labeled_block(label: str, text: str) -> dict:
    """A paragraph like the studio template: bold label, line break, then the text."""
    return {
        "type": "paragraph",
        "content": [
            {"type": "text", "text": label, "marks": [{"type": "strong"}]},
            {"type": "hardBreak"},
            {"type": "text", "text": text},
        ],
    }


def _build_description_adf(issue: dict) -> dict:
    """Build the Jira description (ADF) matching the studio's bug template:
    an ordered list of repro steps, then **Actual Result:** and **Expected Result:**.
    """
    content: list[dict] = []

    steps = issue.get("repro_steps") or []
    if steps:
        content.append({
            "type": "orderedList",
            "attrs": {"order": 1},
            "content": [
                {"type": "listItem", "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": str(s)}]}
                ]}
                for s in steps
            ],
        })

    if issue.get("actual_result"):
        content.append(_adf_labeled_block("Actual Result:", issue["actual_result"]))
    if issue.get("expected_result"):
        content.append(_adf_labeled_block("Expected Result:", issue["expected_result"]))

    # ADF text nodes can't be empty - fall back to the title so we always send a valid doc.
    if not content:
        content.append({"type": "paragraph",
                        "content": [{"type": "text", "text": issue.get("title") or "(no details)"}]})

    return {"type": "doc", "version": 1, "content": content}


def _build_fields(issue: dict) -> dict:
    """The Jira `fields` payload - shared by real push and mock so the saved file
    mirrors exactly what would be sent to Jira."""
    fields = {
        "project": {"key": config.JIRA_PROJECT_KEY},
        "issuetype": {"name": "Bug"},
        "summary": issue.get("title", ""),
        "description": _build_description_adf(issue),
    }
    if issue.get("priority"):
        fields["priority"] = {"name": issue["priority"]}
    if issue.get("labels"):
        fields["labels"] = issue["labels"]
    return fields


def _push_mock(session_dir: Path, draft: dict) -> dict:
    """Mock: append the same `fields` payload we'd POST to Jira, return a fake key."""
    out_file = session_dir / "pushed_issues.json"
    pushed = json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else []
    fake_key = f"MOCK-{len(pushed) + 1}"
    pushed.append({
        "key": fake_key,
        "pushed_at": datetime.now().isoformat(),
        "fields": _build_fields(draft["issue"]),
        "video_clip": draft.get("video_clip"),
        "screenshots": draft.get("screenshots", []),
    })
    out_file.write_text(json.dumps(pushed, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"key": fake_key, "mock": True}


def _attachment_files(session_dir: Path, draft: dict) -> list[Path]:
    """All media to attach: every screenshot + the video clip (if any), in a stable order."""
    names = list(draft.get("screenshots", []))
    if draft.get("video_clip"):
        names.append(draft["video_clip"])
    paths = []
    for name in names:
        p = session_dir / Path(name).name
        if p.exists():
            paths.append(p)
    return paths


def _upload_attachments(issue_key: str, session_dir: Path, draft: dict):
    """Upload all of the bug's screenshots/video to the Jira issue. Best-effort: a failed
    attachment must not fail the whole push (the issue itself is already created)."""
    for path in _attachment_files(session_dir, draft):
        try:
            with open(path, "rb") as f:
                requests.post(
                    f"{config.JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/attachments",
                    auth=(config.JIRA_EMAIL, config.JIRA_API_TOKEN),
                    headers={"X-Atlassian-Token": "no-check"},  # required by Jira for attachments
                    files={"file": (path.name, f)},
                    timeout=60,
                ).raise_for_status()
        except Exception as e:
            print(f"[jira] attachment {path.name} failed: {e}")


def _push_real(session_dir: Path, draft: dict) -> dict:
    resp = requests.post(
        f"{config.JIRA_BASE_URL}/rest/api/3/issue",
        auth=(config.JIRA_EMAIL, config.JIRA_API_TOKEN),
        json={"fields": _build_fields(draft["issue"])},
        timeout=30,
    )
    resp.raise_for_status()
    key = resp.json()["key"]
    _upload_attachments(key, session_dir, draft)
    return {"key": key, "url": f"{config.JIRA_BASE_URL}/browse/{key}", "mock": False}
