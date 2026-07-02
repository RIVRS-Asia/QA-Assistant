"""Push issue to Jira. Default = MOCK MODE: writes issue to pushed_issues.json.

Fill in JIRA_* in .env to push for real (Jira Cloud REST API v3).
"""
import json
from datetime import datetime
from pathlib import Path

import requests

import config
import jira_settings


def push_issue(session_dir: Path, draft: dict, project_key: str | None = None) -> dict:
    """project_key: the project this session is bound to (captured at session start).
    Falls back to the current setting; mock mode when Jira isn't configured."""
    project_key = project_key or jira_settings.get()["project_key"]
    if jira_settings.enabled():
        return _push_real(session_dir, draft, project_key)
    return _push_mock(session_dir, draft, project_key)


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


def _build_fields(issue: dict, project_key: str) -> dict:
    """The Jira `fields` payload - shared by real push and mock so the saved file
    mirrors exactly what would be sent to Jira."""
    fields = {
        "project": {"key": project_key},
        "issuetype": {"name": "Bug"},
        "summary": issue.get("title", ""),
        "description": _build_description_adf(issue),
    }
    if issue.get("priority"):
        fields["priority"] = {"name": issue["priority"]}
    # Jira labels can't contain spaces; always add the tool label so every pushed
    # issue is trackable/deletable via JQL `labels = qa-assistant`.
    labels = [str(l).strip().replace(" ", "-") for l in (issue.get("labels") or []) if l]
    if config.JIRA_LABEL and config.JIRA_LABEL not in labels:
        labels.append(config.JIRA_LABEL)
    fields["labels"] = labels
    return fields


def _push_mock(session_dir: Path, draft: dict, project_key: str) -> dict:
    """Mock: append the same `fields` payload we'd POST to Jira, return a fake key."""
    out_file = session_dir / "pushed_issues.json"
    pushed = json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else []
    fake_key = f"MOCK-{len(pushed) + 1}"
    pushed.append({
        "key": fake_key,
        "pushed_at": datetime.now().isoformat(),
        "fields": _build_fields(draft["issue"], project_key),
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
    s = jira_settings.get()
    for path in _attachment_files(session_dir, draft):
        try:
            with open(path, "rb") as f:
                requests.post(
                    f"{s['base_url']}/rest/api/3/issue/{issue_key}/attachments",
                    auth=(s["email"], s["api_token"]),
                    headers={"X-Atlassian-Token": "no-check"},  # required by Jira for attachments
                    files={"file": (path.name, f)},
                    timeout=60,
                ).raise_for_status()
        except Exception as e:
            print(f"[jira] attachment {path.name} failed: {e}")


def _push_real(session_dir: Path, draft: dict, project_key: str) -> dict:
    s = jira_settings.get()
    resp = requests.post(
        f"{s['base_url']}/rest/api/3/issue",
        auth=(s["email"], s["api_token"]),
        json={"fields": _build_fields(draft["issue"], project_key)},
        timeout=30,
    )
    if not resp.ok:
        # Surface Jira's own message (permission denied, bad field, ...) instead of a bare 500.
        try:
            err = resp.json()
            msg = "; ".join(err.get("errorMessages", []) + list(err.get("errors", {}).values()))
        except Exception:
            msg = resp.text[:200]
        raise ValueError(f"Jira rejected the issue (HTTP {resp.status_code}) for project {project_key}: {msg}")
    key = resp.json()["key"]
    _upload_attachments(key, session_dir, draft)
    return {"key": key, "url": f"{s['base_url']}/browse/{key}", "mock": False}
