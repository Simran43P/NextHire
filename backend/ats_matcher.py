import json
import time
import requests
from typing import Dict, Any

def analyze_job_match(resume_profile: dict, job_description: str) -> Dict[str, Any]:
    """
    Analyzes a resume profile against a job description using Qwen 2.5 via Ollama.
    Returns a structured ATS analysis including a match score and missing skills.
    """
    url = "http://localhost:11434/api/generate"

    prompt = f"""
    You are an expert Applicant Tracking System (ATS) and Technical Recruiter.
    Your task is to analyze the candidate's profile against the provided job description
    and generate a highly detailed ATS match report.

    Rules:
    1. Be highly critical and objective. If the candidate is missing core requirements, score them lower.
    2. Identify specific technical skills, soft skills, and experiences explicitly mentioned in the Job Description.
    3. Cross-reference those requirements with the Candidate Profile.
    4. Calculate a realistic "match_score" from 0 to 100.
    5. List exactly what matches ("matched_skills") and what is missing ("missing_skills").
    6. Provide 2-3 specific, actionable recommendations on how the candidate can improve their resume for this exact role.

    Return ONLY valid JSON matching this exact schema. Do not include markdown formatting.
    {{
      "match_score": 0,
      "matched_skills": ["skill 1", "skill 2"],
      "missing_skills": ["missing 1", "missing 2"],
      "recommendations": ["suggestion 1", "suggestion 2"]
    }}

    Job Description:
    {job_description}

    Candidate Profile:
    {json.dumps(resume_profile, indent=2)}
    """

    payload = {
        "model": "qwen2.5:7b",
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.1 # Keep it low for consistent scoring
        }
    }

    try:
        start = time.time()
        print("Sending ATS Analysis request to Ollama...")
        response = requests.post(url, json=payload, timeout=120)
        print(f"ATS Analysis took {time.time() - start:.2f} seconds")
        response.raise_for_status()

        data = response.json()
        structured_data = json.loads(data["response"])
        
        # Ensure we always return a safe dictionary shape even if the model hallucinates slightly
        return {
            "match_score": structured_data.get("match_score", 0),
            "matched_skills": structured_data.get("matched_skills", []),
            "missing_skills": structured_data.get("missing_skills", []),
            "recommendations": structured_data.get("recommendations", [])
        }

    except Exception as e:
        print(f"Error during ATS Analysis: {e}")
        return {
             "match_score": 0,
             "matched_skills": [],
             "missing_skills": [],
             "recommendations": ["Failed to analyze resume against job description."]
        }