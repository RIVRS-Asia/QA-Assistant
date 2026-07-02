"""Runtime-editable Jira config, persisted to jira_settings.json next to .env.
Seeded from .env on first run; changing it in the UI takes effect without a restart.
Each session captures the current project_key at start, so switching projects only
affects the *next* session (see main.start_session)."""
import json

import requests

import config

_FILE = config.ROOT_DIR / "jira_settings.json"
# base_url / email / api_token ALWAYS come from .env - never persisted (they're secrets,
# and hard-coding the site avoids ever pushing to the wrong Jira). Only project_key is editable.
_settings = {
    "base_url": config.JIRA_BASE_URL,
    "email": config.JIRA_EMAIL,
    "api_token": config.JIRA_API_TOKEN,
    "project_key": config.JIRA_PROJECT_KEY,
}
if _FILE.exists():
    _settings["project_key"] = json.loads(_FILE.read_text(encoding="utf-8")).get("project_key") or _settings["project_key"]


def get() -> dict:
    return dict(_settings)


def enabled() -> bool:
    return bool(_settings["base_url"] and _settings["api_token"] and _settings["project_key"])


def public() -> dict:
    """Settings for the UI - token replaced by a has_token flag so the secret never leaves the server."""
    s = get()
    return {"base_url": s["base_url"], "email": s["email"],
            "project_key": s["project_key"], "has_token": bool(s["api_token"])}


def list_projects() -> list[dict]:
    """Projects on the configured Jira site that can hold a Bug (so push won't fail),
    as [{key, name}]. Raises ValueError if credentials aren't set / are wrong."""
    s = get()
    if not (s["base_url"] and s["email"] and s["api_token"]):
        raise ValueError("Set Jira base_url, email and API token in .env first")
    try:
        r = requests.get(f"{s['base_url']}/rest/api/3/project/search",
                         params={"expand": "issueTypes", "maxResults": 100, "action": "create"},
                         auth=(s["email"], s["api_token"]), timeout=15)
    except requests.RequestException as e:
        raise ValueError(f"Can't reach Jira: {e}")
    if r.status_code in (401, 403):
        raise ValueError("Authentication failed - check email and API token in .env")
    if not r.ok:
        raise ValueError(f"Jira returned HTTP {r.status_code} for {s['base_url']}")
    return [{"key": p["key"], "name": p["name"]}
            for p in r.json().get("values", [])
            if any(t["name"] == "Bug" for t in p.get("issueTypes", []))]


def set_project(project_key: str) -> dict:
    """Persist the chosen project. No Jira round-trip - the key came from list_projects()."""
    project_key = (project_key or "").strip()
    if not project_key:
        raise ValueError("Project key is required")
    _settings["project_key"] = project_key
    _FILE.write_text(json.dumps({"project_key": project_key}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"project_key": project_key}
