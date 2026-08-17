import os
import httpx
import asyncio
from typing import List, Dict, Any
from dotenv import load_dotenv
import traceback

load_dotenv()

# IMPORTANT: Replace this with your actual RapidAPI Key
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = "jsearch.p.rapidapi.com"

if RAPIDAPI_KEY:
    print("✓ RapidAPI key loaded.")
else:
    print("✗ RapidAPI key not found.")

async def fetch_jobs_for_title(title: str, confidence: int, country: str = "in") -> List[Dict[str, Any]]:
    """
    Fetches jobs for a single title using the JSearch API.
    """
    url = "https://jsearch.p.rapidapi.com/search-v2"
    
    # We construct a query like "Frontend Developer in USA"
    querystring = {
        "query": title,
        "country": country,
        "num_pages": 1,
        "date_posted": "month"
    }

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=querystring, timeout=60.0)
            response.raise_for_status()
            data = response.json()

            

            jobs = data.get("data", {}).get("jobs", [])
                        
            standardized_jobs = []
            for job in jobs:
                
                formatted_location = ", ".join(
                    filter(
                        None,
                        [
                            job.get("job_city"),
                            job.get("job_state"),
                            job.get("job_country")
                        ]
                    )
                    or job.get("job_location")
                    or "Location Not specified"
                )

                # We map the JSearch output to a clean, standard schema for your React UI
                standardized_jobs.append({
                    "id": job.get("job_id"),
                    "title": job.get("job_title"),
                    "company": job.get("employer_name") or "Unknown Company",
                    "location": formatted_location,
                    "match": confidence,
                    "type": job.get("job_employment_type"),
                    "description": job.get("job_description"),
                    "apply_link": job.get("job_apply_link") or job.get("job_google_link"),
                    "is_remote": job.get("job_is_remote", False),
                    "posted_at": job.get("job_posted_at_datetime_utc"),
                    "salary":{
                        "max": job.get("job_max_salary"),
                        "min": job.get("job_min_salary")} # Often null, but good to have
                })
            return standardized_jobs
            
            
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error while fetching jobs for {title}")
            print("Status Code:", e.response.status_code)
            print("Response:", e.response.text)
            return []
        
        except Exception as e:
            print(f"\n===== ERROR for {title} =====")
            traceback.print_exc()
            print("=============================\n")
            return []


async def search_all_jobs(job_titles: List[Dict[str, Any]], country: str = "in"): 
    """
    Takes inferred job titles with confidence scores, searches them concurrently, and deduplicates the results.
    """
    # 1. Run all API calls concurrently for maximum speed
    tasks = [fetch_jobs_for_title(job["title"], job["matchPercentage"], country) for job in job_titles]
    results = await asyncio.gather(*tasks)
    
    # 2. Flatten the list of lists into a single list
    all_jobs = [job for sublist in results for job in sublist]
    
    # 3. Deduplicate based on job_id (in case different searches returned the same job)
    unique_jobs = {}
    for job in all_jobs:
        if job["id"] and job["id"] not in unique_jobs:
            unique_jobs[job["id"]] = job
            
    return list(unique_jobs.values())