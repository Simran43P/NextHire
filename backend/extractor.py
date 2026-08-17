
import time
import json
import copy
import requests
from typing import Dict, Any, List



SCHEMA_TEMPLATE: Dict[str, Any] = {
    "name": "",
    "email": "",
    "phone": "",
    "location": "",
    "skills": [],
    "years_of_experience": 0,
    "education": [
        {
            "degree": "",
            "college": "",
            "year": "",
        }
    ],
    "experience": [
        {
            "company": "",
            "designation": "",
            "duration": "",
            "responsibilities": [],
            "achievements": [],
        }
    ],
    "projects": [
        {
            "name": "",
            "description": "",
            "technologies": [],
            "github": "",
            "live_demo": "",
        }
    ],
    "certifications": [],
    "languages": [],
    "links": {
        "github": "",
        "linkedin": "",
        "portfolio": "",
    },
}



def _build_prompt(resume_text: str) -> str:
    """
    Builds the extraction prompt.

    The prompt is intentionally strict and repetitive: local models like
    Qwen 2.5 are much less steerable than frontier hosted models, so
    explicit, unambiguous, repeated constraints materially reduce
    hallucination and formatting drift.
    """
    schema_json = json.dumps(SCHEMA_TEMPLATE, indent=2)

    return f"""You are an expert HR data-extraction assistant.
Your ONLY task is to extract information that is EXPLICITLY present in the resume text below,
and return it as JSON matching the exact schema shown.

STRICT RULES (follow all of them):
1. Do NOT invent, guess, infer, or hallucinate any information that is not explicitly stated in the resume.
2. If a field is not present in the resume, you MUST use the following defaults:
   - Missing string -> ""
   - Missing list -> []
   - Missing integer -> 0
3. Do NOT summarize, rephrase, or embellish. Copy relevant details as they appear in the source text.
4. Return ONLY valid JSON. No markdown, no ```json fences, no explanations, no comments, no trailing text.
5. The JSON keys and nesting MUST exactly match the schema below. Do not add, rename, or remove keys.
6. "years_of_experience" must be a whole number (integer). If it cannot be determined explicitly, use 0.
7. If the resume contains multiple education entries, work experiences, or projects, include all of them
   as separate objects in the corresponding array, each following the same object shape shown below.

Schema (structure only, values below are placeholders/defaults):
{schema_json}

Resume Text:
\"\"\"
{resume_text}
\"\"\"

Return ONLY the JSON object now.
"""



def _fill_defaults(data: Any, template: Any) -> Any:
    """
    Recursively ensures `data` has the same shape as `template`, filling in
    any missing keys/values with the template's defaults.

    Handles three cases:
      - dict: ensure every key in `template` exists in `data`, recursing
        into nested dicts/lists.
      - list of dicts (repeating schema objects like education/experience):
        validate each item in `data` against the single template item.
      - scalars: if `data` is missing or has the wrong type, fall back to
        the template default.
    """
    # Dict case: e.g. the top-level object, or "links"
    if isinstance(template, dict):
        if not isinstance(data, dict):
            data = {}
        result = {}
        for key, default_value in template.items():
            result[key] = _fill_defaults(data.get(key), default_value)
        return result

    # List case: e.g. "skills" (list of scalars) or "education" (list of dicts)
    if isinstance(template, list):
        if not isinstance(data, list):
            return []
        # If the template list contains a dict, treat it as the shape for
        # every item in the returned list (e.g. education/experience/projects).
        if template and isinstance(template[0], dict):
            item_template = template[0]
            return [_fill_defaults(item, item_template) for item in data]
        # Otherwise it's a simple list (e.g. list of strings) - keep as-is.
        return data

    # Scalar case: string or int defaults
    if isinstance(template, bool):
        return data if isinstance(data, bool) else template
    if isinstance(template, int):
        return data if isinstance(data, int) and not isinstance(data, bool) else template
    if isinstance(template, str):
        return data if isinstance(data, str) else template

    return data if data is not None else template


def _validate_profile(raw_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Public-facing wrapper around _fill_defaults that guarantees the
    returned profile always matches SCHEMA_TEMPLATE exactly, regardless of
    what the model actually produced.
    """
    return _fill_defaults(raw_profile, copy.deepcopy(SCHEMA_TEMPLATE))



def extract_resume_data(
    resume_text: str,
    model: str = "qwen2.5:7b",
    ollama_url: str = "http://localhost:11434/api/generate",
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """
    Sends raw resume text to a local Qwen 2.5 model via Ollama and returns a
    structured, schema-validated profile.

    Args:
        resume_text: Raw resume text to extract structured data from.
        model: Ollama model tag to use.
        ollama_url: Ollama /api/generate endpoint.
        timeout_seconds: Request timeout in seconds.

    Returns:
        A dict of the shape:
        {
            "success": bool,
            "profile": dict | None,
            "raw_text": str,
            "error": str | None,
        }
    """
    
    # print("Building prompt for Ollama...")
    prompt = _build_prompt(resume_text)
    # print("Prompt built.")
    
    payload = {
        "model": model,
        "prompt": prompt,
        "format": "json",  # Ask Ollama to constrain output to valid JSON.
        "stream": False,
        "options": {
            # Deterministic generation: same input -> same output every time.
            "temperature": 0,
            "top_p": 0,
            "top_k": 1,
            "repeat_penalty": 1.0,
            "seed": 42,
            # Large context window so long, multi-page resumes aren't truncated.
            "num_ctx": 8192,
        },
    }

    try:
        start = time.time()
        print(f"Resume text length: {len(resume_text)} characters")
        print(f"Prompt length: {len(prompt)} characters")
        print(f"Approx prompt tokens: {len(prompt)//4}")
        print("Sending request to Ollama...")
        response = requests.post(ollama_url, json=payload, timeout=timeout_seconds)
        print(f"Ollama request took {time.time() - start:.2f} seconds")
        # print("Received response from Ollama")
        response.raise_for_status()

        data = response.json()
        # print("Converted HTTP response to Python dict.")

        try:
            raw_profile = json.loads(data["response"])
            print("LLM JSON parsed successfully.")
        except (json.JSONDecodeError, KeyError):
            return {
                "success": False,
                "profile": None,
                "raw_text": resume_text,
                "error": "Model did not return valid JSON.",
            }

        # Guarantee the schema is always complete, even if the model
        # dropped fields or added incorrect types.
        validated_profile = _validate_profile(raw_profile)
        # print(json.dumps(validated_profile, indent=2))

        return {
            "success": True,
            "profile": validated_profile,
            "raw_text": resume_text,
            "error": None,
        }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "profile": None,
            "raw_text": resume_text,
            "error": f"Request to Ollama timed out after {timeout_seconds} seconds.",
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "profile": None,
            "raw_text": resume_text,
            "error": f"Failed to communicate with Ollama: {e}",
        }


if __name__ == "__main__":
    sample_resume = """
    Jane Doe
    jane.doe@example.com | +1-555-123-4567 | San Francisco, CA

    Skills: Python, SQL, Machine Learning

    Experience:
    Data Scientist at Acme Corp (2021 - Present)
    - Built churn prediction models
    - Reduced customer churn by 12%
    """
    result = extract_resume_data(sample_resume)
    print(json.dumps(result, indent=2))