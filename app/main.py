import os
import uuid
import datetime
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db, engine, Base
from app.models import Job, Transaction, JobSummary
from app.schemas import (
    UploadResponse, JobStatusResponse, JobStatusSummary,
    JobResultsResponse, JobListItem, TransactionSchema, NarrativeSummarySchema
)
from app.tasks import process_transaction_csv
# Create database tables on startup
Base.metadata.create_all(bind=engine)

def print_banner():
    banner = """╭──────────────────────────────────────────────────────────────────────────────╮
│                                                                              │
│                                                                              │
│        ___    ____   ____  ____  ____  ________  __                          │
│       /   |  /  _/  / __ \/ __ \/ __ \/ ____/ / / /                          │
│      / /| |  / /   / /_/ / / / / / / / / __/ /_/ /                           │
│     / ___ |_/ /   / ____/ /_/ / /_/ / /_/ / __  /                            │
│    /_/  |_/___/  /_/    \____/\____/\____/_/ /_/                             │
│                                                                              │
│                                                                              │
│                                                                              │
╰───────────────── AI Transaction Processing Pipeline v1.0.0 ──────────────────╯"""
    print(banner)
    print("                    Available API Endpoints")
    print(" Method   Endpoint             Description                     ")
    print(" POST     /jobs/upload         Upload CSV and start processing ")
    print(" GET      /jobs/{id}/status    Check job processing status     ")
    print(" GET      /jobs/{id}/results   Retrieve full analysis results  ")
    print(" GET      /jobs                List all transaction jobs       ")
    print(" GET      /docs                Interactive Swagger UI          ")
    print("\nSystem online. All services responding.\n")

print_banner()

app = FastAPI(
    title="AI-Powered Transaction Processing Pipeline API",
    description="Backend API for uploading, cleaning, and analyzing financial transaction CSVs using Celery and Gemini LLM.",
    version="1.0.0"
)

# Enable CORS for convenience
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/jobs/upload", response_model=UploadResponse, status_code=202)
def upload_transactions_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Accept a CSV file upload. Validate it, create a Job record in the database
    with status=pending, enqueue the processing task, and return the job_id immediately.
    """
    # 1. Validate file extension
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Only CSV files are supported."
        )
        
    # 2. Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # 3. Save uploaded file to disk
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}.csv")
    try:
        with open(file_path, "wb") as f:
            f.write(file.file.read())
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save uploaded file: {str(e)}"
        )
        
    # 4. Create Job record in the database
    new_job = Job(
        id=job_id,
        filename=file.filename,
        status="pending",
        row_count_raw=0,
        row_count_clean=0,
        created_at=datetime.datetime.utcnow()
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    
    # 5. Enqueue background processing task
    process_transaction_csv.delay(job_id, file_path)
    
    return UploadResponse(
        job_id=job_id,
        filename=file.filename,
        status="pending",
        message="CSV file uploaded successfully. Processing has started asynchronously."
    )


@app.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """
    Return the current status of the job: pending, processing, completed, or failed.
    If completed, also include a summary field with high-level stats.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    response = JobStatusResponse(job_id=job.id, status=job.status)
    
    if job.status == "completed" and job.summary:
        summary_data = JobStatusSummary(
            filename=job.filename,
            status=job.status,
            row_count_raw=job.row_count_raw,
            row_count_clean=job.row_count_clean,
            created_at=job.created_at,
            completed_at=job.completed_at,
            total_spend_inr=job.summary.total_spend_inr,
            total_spend_usd=job.summary.total_spend_usd,
            anomaly_count=job.summary.anomaly_count,
            risk_level=job.summary.risk_level
        )
        response.summary = summary_data
        
    return response


@app.get("/jobs/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(job_id: str, db: Session = Depends(get_db)):
    """
    Return the full structured output: cleaned transactions list, flagged anomalies,
    per-category spend breakdown, and the LLM-generated narrative summary.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job results are not available yet. Job status is: {job.status}"
        )
        
    # 1. Cleaned transactions
    cleaned_txs = [TransactionSchema.model_validate(tx) for tx in job.transactions]
    
    # 2. Flagged anomalies
    anomalies = [TransactionSchema.model_validate(tx) for tx in job.transactions if tx.is_anomaly]
    
    # 3. Category spend breakdown
    # e.g., {"INR": {"Food": 100.0, ...}, "USD": {"Shopping": 50.0}}
    breakdown = {}
    for tx in job.transactions:
        curr = tx.currency or "INR"
        cat = tx.category or "Uncategorised"
        amt = tx.amount or 0.0
        
        if curr not in breakdown:
            breakdown[curr] = {}
            
        breakdown[curr][cat] = round(breakdown[curr].get(cat, 0.0) + amt, 2)
        
    # 4. LLM Summary
    summary_schema = None
    if job.summary:
        summary_schema = NarrativeSummarySchema.model_validate(job.summary)
        
    return JobResultsResponse(
        job_id=job.id,
        filename=job.filename,
        status=job.status,
        row_count_raw=job.row_count_raw,
        row_count_clean=job.row_count_clean,
        created_at=job.created_at,
        completed_at=job.completed_at,
        cleaned_transactions=cleaned_txs,
        flagged_anomalies=anomalies,
        category_breakdown=breakdown,
        llm_summary=summary_schema
    )


@app.get("/jobs", response_model=List[JobListItem])
def list_jobs(
    status: Optional[str] = Query(None, description="Filter jobs by status (pending, processing, completed, failed)"),
    db: Session = Depends(get_db)
):
    """
    List all jobs with their status, filename, row count, and created_at timestamp.
    Supports filtering via ?status= query parameter.
    """
    query = db.query(Job)
    
    if status:
        query = query.filter(Job.status == status.lower().strip())
        
    jobs = query.order_by(Job.created_at.desc()).all()
    return [JobListItem.model_validate(job) for job in jobs]


@app.get("/")
def read_root():
    return {
        "message": "Welcome to the AI-Powered Transaction Processing Pipeline API!",
        "docs_url": "/docs",
        "redoc_url": "/redoc"
    }
