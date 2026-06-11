from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

# Job Upload Response
class UploadResponse(BaseModel):
    job_id: str
    filename: str
    status: str
    message: str

# High-level stats for job status response
class JobStatusSummary(BaseModel):
    filename: str
    status: str
    row_count_raw: int
    row_count_clean: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    total_spend_inr: float
    total_spend_usd: float
    anomaly_count: int
    risk_level: str

# Job Status Response
class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    summary: Optional[JobStatusSummary] = None

# Individual Transaction Schema
class TransactionSchema(BaseModel):
    id: int
    txn_id: Optional[str] = None
    date: Optional[str] = None
    merchant: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    account_id: Optional[str] = None
    notes: Optional[str] = None
    is_anomaly: bool
    anomaly_reason: Optional[str] = None
    llm_category: bool
    llm_failed: bool

    class Config:
        from_attributes = True

# Job Narrative Summary Schema
class NarrativeSummarySchema(BaseModel):
    total_spend_inr: float
    total_spend_usd: float
    top_merchants: List[Dict[str, Any]]
    anomaly_count: int
    narrative: str
    risk_level: str

    class Config:
        from_attributes = True

# Job Results Response Schema
class JobResultsResponse(BaseModel):
    job_id: str
    filename: str
    status: str
    row_count_raw: int
    row_count_clean: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    # Required sections
    cleaned_transactions: List[TransactionSchema]
    flagged_anomalies: List[TransactionSchema]
    category_breakdown: Dict[str, Dict[str, float]] # e.g. {"INR": {"Food": 100.0}, "USD": {"Shopping": 50.0}}
    llm_summary: Optional[NarrativeSummarySchema] = None

    class Config:
        from_attributes = True

# Job List Item
class JobListItem(BaseModel):
    id: str
    filename: str
    status: str
    row_count_raw: int
    row_count_clean: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True
