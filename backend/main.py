from fastapi import FastAPI, File, UploadFile, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF
import io
import traceback

#Import the AI logic modules
from extractor import extract_resume_data
from infer_titles import infer_job_titles
from job_search import search_all_jobs

# Initialize the FastAPI app
app = FastAPI(
    title="NextHire Core API",
    description="Backend services for the Job Application AI Agent",
    version="1.0.0"
)

# Configure CORS so your React frontend can talk to this API
# (By default React runs on port 5173 or 3000, and FastAPI on 8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace "*" with your actual frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "NextHire API is running!"}

@app.post("/api/parse-resume")
async def parse_resume(file: UploadFile = File(...)):
    """
    Accepts a PDF file upload, extracts the raw text using PyMuPDF, 
    and returns it to the client.
    """
    # 1. Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are currently supported.")

    try:
        # 2. Read the file into memory
        content = await file.read()
        
        # 3. Open the PDF with PyMuPDF
        # We use stream=content because the file is in memory, not saved to the hard drive
        pdf_document = fitz.open(stream=content, filetype="pdf")
        extracted_text = ""
        
        # 4. Iterate through pages and extract text
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            # You can experiment with get_text("blocks") later for better layout retention
            extracted_text += page.get_text("text") + "\n"
            
        pdf_document.close()

        extraction_result = extract_resume_data(extracted_text.strip()) 

        if not extraction_result["success"]:
            raise HTTPException(
                status_code=500,
                detail=extraction_result["error"]
            )
            print(extraction_result)


        print("Resume extraction completed.")
        profile_json = extraction_result["profile"]

        
        
        # 5. Return the extracted text
        return {
            "status": "success",
            "filename": file.filename,
            "profile": profile_json,
            # "inferred_job_titles": inferred_titles,
            "raw_text": extracted_text.strip(),
            "message": "Resume parsed successfully."
        }
        
    except Exception as e:
        # Catch any errors (like corrupted PDFs) and return a 500 error
        print("\n========== ERROR ==========")
        traceback.print_exc()
        print("===========================\n")
        raise HTTPException(status_code=500, detail=f"An error occurred while parsing the PDF: {str(e)}")

@app.post("/api/infer-titles")
async def api_infer_titles(profile:dict = Body(...)):
    """
    Accepts a structured resume profile(JSON) and returns inferred job titles.
    """
    try:
        print("Calling infer_job_titles...")
        inferred_titles = infer_job_titles(profile)
        print("Returned from infer_job_titles.")
        

        formatted_titles = []
        for i , job in enumerate(inferred_titles):
            formatted_titles.append({
                "id": f"title-{i}",
                "title": job.get("title", "Unknown"),
                "matchPercentage": job.get("confidence", 0)
            })

        return {"status": "success", "titles": formatted_titles}
    except Exception as e:
        print("\n========== INFERENCE ERROR ==========")
        traceback.print_exc()
        print("=====================================\n")
        raise HTTPException(status_code=500, detail=f"Inference failed: {str(e)}")

@app.post("/api/jobs")
async def api_search_jobs(
    job_titles : list[dict] = Body(...),
    country: str = "in"
):
    try: 
        jobs = await search_all_jobs(job_titles, country)

        return {
            "status": "success",
            "jobs": jobs
        }
    
    except Exception as e:
        print("\n========== JOB SEARCH ERROR ==========")
        traceback.print_exc()
        print("======================================\n")

        raise HTTPException(
            status_code=500,
            detail=f"Job search failed: {str(e)}"
        )