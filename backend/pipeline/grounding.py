"""Locate the buggy region on a screenshot from the QA's verbal description.

Sends the screenshot + the (Vietnamese) transcript to Gemini and asks for ONE bounding
box around the area the tester is calling broken. Returns [ymin, xmin, ymax, xmax]
normalized to 0-1000 (Gemini's native box format), or None when there's no key, no clear
region, or any error - the auto-mark is a best-effort SUGGESTION, never required.
"""
import json
from pathlib import Path

import config

BOX_PROMPT = """A Vietnamese QA tester described a bug in this game screenshot:

"{description}"

Return the bounding box of the SINGLE region in the image the tester is describing as
buggy (the UI element, object, or area they refer to). Respond with ONLY a JSON array
[ymin, xmin, ymax, xmax] of integers 0-1000 normalized to the image size. If you cannot
confidently locate the region, respond with exactly: null"""


def locate_bug(image_path, description: str) -> list[int] | None:
    description = (description or "").strip()
    if not config.GEMINI_API_KEY or not description:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=config.GEMINI_API_KEY)
        img_bytes = Path(image_path).read_bytes()
        resp = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[
                BOX_PROMPT.format(description=description),
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
            ],
            # temperature=0: grounding must be deterministic - same image+description should always
            # give the same (highest-confidence) box. The default temperature re-rolls a different,
            # often worse box on every call, which made reprocess randomly move the annotation.
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
        )
        return _pad_box(_parse_box(resp.text or ""))
    except Exception as e:
        print(f"[grounding] error, no auto-mark: {e}")
        return None


def _parse_box(text: str) -> list[int] | None:
    try:
        box = json.loads(text.strip())
    except Exception:
        return None
    if not isinstance(box, list) or len(box) != 4:
        return None
    if all(0 <= n <= 1000 for n in box) and box[0] < box[2] and box[1] < box[3]:
        return box
    return None


def _pad_box(box: list[int] | None, pad: int = 20) -> list[int] | None:
    # ponytail: pad=20 ~2% margin on 0-1000 scale, covers Gemini's typical localization drift
    if not box:
        return None
    ymin, xmin, ymax, xmax = box
    return [max(0, ymin - pad), max(0, xmin - pad), min(1000, ymax + pad), min(1000, xmax + pad)]
