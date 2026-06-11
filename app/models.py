import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, index=True) # UUID
    filename = Column(String, nullable=False)
    status = Column(String, default="pending") # pending, processing, completed, failed
    row_count_raw = Column(Integer, default=0)
    row_count_clean = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    transactions = relationship("Transaction", back_populates="job", cascade="all, delete-orphan")
    summary = relationship("JobSummary", uselist=False, back_populates="job", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    txn_id = Column(String, nullable=True)
    date = Column(String, nullable=True) # ISO 8601 date string YYYY-MM-DD
    merchant = Column(String, nullable=True)
    amount = Column(Float, nullable=True)
    currency = Column(String, nullable=True) # USD / INR
    status = Column(String, nullable=True) # SUCCESS / FAILED / PENDING
    category = Column(String, nullable=True) # Filled with Uncategorised if empty initially
    account_id = Column(String, nullable=True)
    notes = Column(Text, nullable=True) # Notes from the CSV
    
    # Anomaly tracking
    is_anomaly = Column(Boolean, default=False)
    anomaly_reason = Column(Text, nullable=True)

    # LLM classification tracking
    llm_category = Column(Boolean, default=False) # Whether category was filled by LLM
    llm_raw_response = Column(Text, nullable=True)
    llm_failed = Column(Boolean, default=False)

    job = relationship("Job", back_populates="transactions")


class JobSummary(Base):
    __tablename__ = "job_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False, unique=True)
    total_spend_inr = Column(Float, default=0.0)
    total_spend_usd = Column(Float, default=0.0)
    top_merchants = Column(JSON, nullable=True) # JSON representation of top merchants e.g., [{"merchant": "Swiggy", "spend": 1000}, ...]
    anomaly_count = Column(Integer, default=0)
    narrative = Column(Text, nullable=True)
    risk_level = Column(String, default="low") # low / medium / high

    job = relationship("Job", back_populates="summary")
