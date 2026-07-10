import re
import json


def parse_llm_json(text: str) -> dict:
    """
    Robustly extract a JSON object from an LLM response.
    Handles: plain JSON, markdown fences (```json ... ```), extra prose around the object.
    Raises ValueError if no valid JSON object is found.
    """
    text = text.strip()

    # Fast path — response is already clean JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the first {...} block anywhere in the text (handles fences + prose)
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON object found in LLM response:\n{text[:400]}")