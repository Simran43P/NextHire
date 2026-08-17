import json
import time
import requests
from typing import List, Dict


def infer_job_titles(resume_profile: dict) -> List[Dict]:
    """
    Analyzes a structured resume profile using Qwen 2.5 via Ollama
    and infers the top 5 most suitable job titles for the candidate,
    each with a confidence score.
    """
    url = "http://localhost:11434/api/generate"

    # We pass the parsed resume JSON back into the LLM and ask it to act as
    # an entry-level/early-career technical recruiter, ranking realistic
    # job titles by confidence.
    prompt = f"""
    You are an expert technical recruiter specializing in entry-level and early-career hiring.
    Analyze the candidate profile below and infer the TOP 5 most suitable and realistic job titles
    they should apply for.

    Prioritize signals in this order:
    1. Technical skills
    2. Technologies used in projects
    3. Internship experience (if available)
    4. Previous work experience (if available)
    5. Education
    6. Certifications

    Rules:
    - If the candidate is a fresher with little or no work experience, infer entry-level job
      titles based primarily on their projects and skills. Do NOT penalize the candidate for
      lacking experience.
    - Only recommend job titles that are commonly found on real job boards
      (e.g. LinkedIn, Greenhouse, Lever, Indeed, RemoteOK, Arbeitnow).
    - Do NOT invent creative, non-standard, or made-up job titles.
    - Do NOT recommend senior or managerial positions unless clearly justified by the
      candidate's experience.
    - Remove duplicate or nearly identical job titles.
    - Rank the job titles from best match to least match.
    - Assign a confidence score from 0 to 100 for every job title, reflecting how well the
      candidate's profile matches that title.

    Return ONLY valid JSON matching this exact schema. Do not include markdown formatting,
    explanations, or any text outside the JSON object.
    {{
        "job_titles": [
            {{
                "title": "Frontend Developer",
                "confidence": 95
            }}
        ]
    }}

    Candidate Profile:
    {json.dumps(resume_profile, indent=2)}
    """

    payload = {
        "model": "qwen2.5:7b",
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.2
        }
    }

    try:
        start = time.time()
        response = requests.post(url, json=payload, timeout=90)
        print(f"Ollama request took {time.time() - start:.2f} seconds")
        response.raise_for_status()

        data = response.json()
        structured_data = json.loads(data["response"])

        job_titles = _validate_job_titles(structured_data)
        job_titles =  _deduplicate_job_titles(job_titles)

        print("\n=== Inferred Job Titles ===")
        for job in job_titles:
            print(f"{job['title']} ({job.get('confidence', 0)}%)")
        return job_titles
        

    except requests.exceptions.RequestException as e:
        print(f"Error communicating with Ollama during inference: {e}")
        return []
    except json.JSONDecodeError:
        print("Error decoding the JSON from the model during inference.")
        return []


def _validate_job_titles(structured_data: dict) -> List[Dict]:
    """
    Validates that the model output contains a well-formed "job_titles" list.
    Returns an empty list if the structure is missing or malformed instead
    of raising an exception, so callers never have to handle bad model
    output themselves.
    """
    job_titles = structured_data.get("job_titles")

    if not isinstance(job_titles, list):
        return []

    # Keep only well-formed entries (must have a non-empty string title).
    valid_titles = [
        entry for entry in job_titles
        if isinstance(entry, dict) and isinstance(entry.get("title"), str) and entry["title"].strip()
    ]

    return valid_titles


def _deduplicate_job_titles(job_titles: List[Dict]) -> List[Dict]:
    """
    Removes duplicate job titles using a case-insensitive comparison,
    preserving the original ordering. If duplicates exist, the entry with
    the highest confidence score is kept in that title's original position.
    """
    seen_titles: Dict[str, Dict] = {}
    ordered_keys: List[str] = []

    for entry in job_titles:
        title_key = entry["title"].strip().lower()
        confidence = entry.get("confidence", 0)

        if title_key not in seen_titles:
            seen_titles[title_key] = entry
            ordered_keys.append(title_key)
        else:
            # Duplicate found: keep whichever version has the higher confidence.
            existing_confidence = seen_titles[title_key].get("confidence", 0)
            if confidence > existing_confidence:
                seen_titles[title_key] = entry

    return [seen_titles[key] for key in ordered_keys]

