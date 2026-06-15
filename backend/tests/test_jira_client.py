"""Tests for jira_client — mock the Jira REST API so no real board is touched.

Run from the backend/ dir:
    ./.venv/Scripts/python.exe -m pytest tests/ -v
"""
import json

import pytest
import responses

import config
import jira_client


@pytest.fixture
def sample_draft():
    return {
        "issue": {
            "title": "Player falls through floor on level 2",
            "repro_steps": ["Load level 2", "Walk to the north wall", "Jump"],
            "actual_result": "Character clips through the floor mesh and falls forever.",
            "expected_result": "Character should collide with the floor.",
            "priority": "High",
            "labels": ["MUST_FIX"],
        },
        "video_clip": "clip.mp4",
        "screenshots": ["shot1.png"],
    }


# --------------------------- mock mode ---------------------------

def test_push_mock_writes_file_and_returns_fake_key(tmp_path, sample_draft, monkeypatch):
    monkeypatch.setattr(config, "JIRA_ENABLED", False)

    result = jira_client.push_issue(tmp_path, sample_draft)

    assert result == {"key": "MOCK-1", "mock": True}
    pushed = json.loads((tmp_path / "pushed_issues.json").read_text(encoding="utf-8"))
    assert len(pushed) == 1
    assert pushed[0]["key"] == "MOCK-1"
    # Mock stores the same Jira `fields` payload that real mode would POST.
    fields = pushed[0]["fields"]
    assert fields["summary"] == sample_draft["issue"]["title"]
    assert fields["issuetype"]["name"] == "Bug"
    assert fields["description"]["content"][0]["type"] == "orderedList"


def test_push_mock_increments_key(tmp_path, sample_draft, monkeypatch):
    monkeypatch.setattr(config, "JIRA_ENABLED", False)

    jira_client.push_issue(tmp_path, sample_draft)
    second = jira_client.push_issue(tmp_path, sample_draft)

    assert second["key"] == "MOCK-2"
    pushed = json.loads((tmp_path / "pushed_issues.json").read_text(encoding="utf-8"))
    assert len(pushed) == 2


# --------------------------- real mode (mocked HTTP) ---------------------------

@pytest.fixture
def jira_config(monkeypatch):
    monkeypatch.setattr(config, "JIRA_ENABLED", True)
    monkeypatch.setattr(config, "JIRA_BASE_URL", "https://test.atlassian.net")
    monkeypatch.setattr(config, "JIRA_EMAIL", "qa@example.com")
    monkeypatch.setattr(config, "JIRA_API_TOKEN", "fake-token")
    monkeypatch.setattr(config, "JIRA_PROJECT_KEY", "TEST")


@responses.activate
def test_push_real_posts_to_jira_and_returns_key(tmp_path, sample_draft, jira_config):
    responses.add(
        responses.POST,
        "https://test.atlassian.net/rest/api/3/issue",
        json={"key": "TEST-123"},
        status=201,
    )

    result = jira_client.push_issue(tmp_path, sample_draft)

    assert result == {
        "key": "TEST-123",
        "url": "https://test.atlassian.net/browse/TEST-123",
        "mock": False,
    }

    # Verify the request payload sent to "Jira" without ever hitting a real server.
    assert len(responses.calls) == 1
    sent = json.loads(responses.calls[0].request.body)
    fields = sent["fields"]
    assert fields["project"]["key"] == "TEST"
    assert fields["issuetype"]["name"] == "Bug"
    assert fields["summary"] == sample_draft["issue"]["title"]
    assert fields["priority"] == {"name": "High"}
    assert fields["labels"] == ["MUST_FIX"]
    # repro_steps -> leading orderedList; actual/expected -> bold-labeled paragraphs.
    blocks = fields["description"]["content"]
    assert blocks[0]["type"] == "orderedList"
    step1 = blocks[0]["content"][0]["content"][0]["content"][0]["text"]
    assert step1 == "Load level 2"
    labels = [b["content"][0]["text"] for b in blocks if b["type"] == "paragraph"]
    assert "Actual Result:" in labels
    assert "Expected Result:" in labels


@responses.activate
def test_push_real_without_repro_steps(tmp_path, jira_config):
    draft = {"issue": {"title": "Crash", "actual_result": "App crashes."}}
    responses.add(
        responses.POST,
        "https://test.atlassian.net/rest/api/3/issue",
        json={"key": "TEST-9"},
        status=201,
    )

    result = jira_client.push_issue(tmp_path, draft)

    assert result["key"] == "TEST-9"
    sent = json.loads(responses.calls[0].request.body)
    blocks = sent["fields"]["description"]["content"]
    assert all(b["type"] != "orderedList" for b in blocks)


@responses.activate
def test_push_real_raises_on_api_error(tmp_path, sample_draft, jira_config):
    responses.add(
        responses.POST,
        "https://test.atlassian.net/rest/api/3/issue",
        json={"errorMessages": ["Invalid project"]},
        status=400,
    )

    with pytest.raises(Exception):  # requests.HTTPError from raise_for_status()
        jira_client.push_issue(tmp_path, sample_draft)
