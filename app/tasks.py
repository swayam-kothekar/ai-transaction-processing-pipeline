import os
import json
import datetime
import traceback
import pandas as pd
from celery import shared_task
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import Job, Transaction, JobSummary
from app.llm import classify_transactions_batch, generate_narrative_summary, rule_based_fallback_categorization
from rich.console import Console
from rich.theme import Theme

custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red",
    "success": "green",
    "job": "bold magenta",
})
console = Console(theme=custom_theme)

@celery_app.task(name="app.tasks.process_transaction_csv")
def process_transaction_csv(job_id: str, file_path: str):
    """
    Asynchronous Celery task to process the uploaded transaction CSV file.
    """
    db = SessionLocal()
    
    # 1. Update Job status to processing
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        console.print(f"[error]Job {job_id} not found in database.[/error]")
        db.close()
        return
        
    console.print(f"[job]JOB {job_id}[/job]: [info]Status changed to PROCESSING[/info]")
    job.status = "processing"
    db.commit()
    
    try:
        # 2. Check if file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Uploaded CSV file not found at {file_path}")
            
        # 3. Read raw CSV
        console.print(f"[job]JOB {job_id}[/job]: [info]Reading CSV file...[/info]")
        # We handle potential empty/blank values properly
        df_raw = pd.read_csv(file_path, keep_default_na=False, na_values=[''])
        row_count_raw = len(df_raw)
        job.row_count_raw = row_count_raw
        db.commit()
        
        if row_count_raw == 0:
            raise ValueError("The uploaded CSV file is empty.")
            
        # 4. Data Cleaning
        console.print(f"[job]JOB {job_id}[/job]: [info]Executing data cleaning pipeline...[/info]")
        # ... rest of cleaning logic ...
        df = df_raw.copy()
        
        # a) Normalize date formats to ISO 8601 (YYYY-MM-DD)
        def parse_date(date_val):
            if pd.isna(date_val):
                return None
            date_str = str(date_val).strip()
            for fmt in ("%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d"):
                try:
                    return pd.to_datetime(date_str, format=fmt).strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    pass
            # Fallback parsing
            try:
                return pd.to_datetime(date_str).strftime("%Y-%m-%d")
            except Exception:
                return date_str
                
        df['date'] = df['date'].apply(parse_date)
        
        # b) Strip currency symbols from amounts
        def clean_amount(val):
            if pd.isna(val):
                return 0.0
            if isinstance(val, (int, float)):
                return float(val)
            val_str = str(val).replace("$", "").replace(",", "").strip()
            try:
                return float(val_str)
            except ValueError:
                return 0.0
                
        df['amount'] = df['amount'].apply(clean_amount)
        
        # c) Uppercase status values
        df['status'] = df['status'].fillna('PENDING').astype(str).str.strip().str.upper()
        # Keep status within SUCCESS, FAILED, PENDING. If anything else, default to PENDING.
        df['status'] = df['status'].apply(lambda x: x if x in ['SUCCESS', 'FAILED', 'PENDING'] else 'PENDING')
        
        # d) Clean currency casing
        df['currency'] = df['currency'].fillna('INR').astype(str).str.strip().str.upper()
        
        # e) Track missing categories before filling them
        df['originally_empty_category'] = df['category'].isna() | (df['category'].astype(str).str.strip() == '')
        df['category'] = df['category'].fillna('Uncategorised').astype(str).str.strip()
        df.loc[df['category'] == '', 'category'] = 'Uncategorised'
        
        # f) Remove exact duplicate rows
        # Drop duplicates based on all columns except index
        df = df.drop_duplicates().reset_index(drop=True)
        row_count_clean = len(df)
        job.row_count_clean = row_count_clean
        db.commit()
        
        # 5. Anomaly Detection
        console.print(f"[job]JOB {job_id}[/job]: [info]Performing anomaly detection...[/info]")
        # Calculate median amount per account_id (using cleaned amounts)
        medians = df.groupby('account_id')['amount'].median().to_dict()
        
        df['is_anomaly'] = False
        df['anomaly_reason'] = ""
        
        domestic_brands = ["swiggy", "ola", "irctc"]
        
        for idx, row in df.iterrows():
            reasons = []
            acc_id = row['account_id']
            amount = row['amount']
            currency = row['currency']
            merchant = str(row['merchant']).lower()
            
            # Anomaly 1: amount exceeds 3x the account's median
            if pd.notna(acc_id) and acc_id in medians:
                median_val = medians[acc_id]
                if amount > 3 * median_val:
                    reasons.append(f"Amount exceeds 3x account median ({median_val:.2f})")
                    
            # Anomaly 2: currency is USD but merchant is domestic-only brand
            if currency == "USD" and any(brand in merchant for brand in domestic_brands):
                reasons.append(f"USD used for domestic merchant ({row['merchant']})")
                
            if reasons:
                df.at[idx, 'is_anomaly'] = True
                df.at[idx, 'anomaly_reason'] = " | ".join(reasons)
                
        # 6. LLM Classification (Batching calls)
        # Identify rows needing classification
        to_classify_mask = df['originally_empty_category']
        to_classify_indices = df[to_classify_mask].index.tolist()
        
        console.print(f"[job]JOB {job_id}[/job]: [info]LLM Categorization for {len(to_classify_indices)} transactions...[/info]")
        
        df['llm_category'] = False
        df['llm_failed'] = False
        df['llm_raw_response'] = ""
        
        # Batch size of 15
        batch_size = 15
        for i in range(0, len(to_classify_indices), batch_size):
            batch_idxs = to_classify_indices[i:i+batch_size]
            # ... rest of batching logic ...
            batch_data = []
            for idx in batch_idxs:
                row = df.loc[idx]
                batch_data.append({
                    "id": int(idx),
                    "merchant": row['merchant'],
                    "amount": row['amount'],
                    "notes": row['notes'] if pd.notna(row['notes']) else ""
                })
                
            try:
                # Call batch classification
                classifications = classify_transactions_batch(batch_data)
                
                # Apply classifications to DataFrame
                for item in classifications:
                    t_idx = item.get("id")
                    category = item.get("category")
                    llm_failed = item.get("llm_failed", False)
                    
                    if t_idx is not None and t_idx in batch_idxs:
                        df.at[t_idx, 'category'] = category
                        df.at[t_idx, 'llm_category'] = True
                        df.at[t_idx, 'llm_failed'] = llm_failed
                        df.at[t_idx, 'llm_raw_response'] = json.dumps(item)
            except Exception as batch_err:
                console.print(f"[error]Batch classification error for indices {batch_idxs}: {batch_err}[/error]")
                # Mark entire batch as failed but continue
                for idx in batch_idxs:
                    df.at[idx, 'llm_failed'] = True
                    df.at[idx, 'llm_category'] = False
                    # Fallback to rule-based classification so they have something
                    fallback_item = rule_based_fallback_categorization([{
                        "id": int(idx),
                        "merchant": df.at[idx, 'merchant'],
                        "notes": df.at[idx, 'notes'] if pd.notna(df.at[idx, 'notes']) else ""
                    }])[0]
                    df.at[idx, 'category'] = fallback_item["category"]
                    
        # 7. Write cleaned transactions to the database
        console.print(f"[job]JOB {job_id}[/job]: [info]Persisting {len(df)} transactions to DB...[/info]")
        db_transactions = []
        # ... bulk save ...
        for _, row in df.iterrows():
            txn = Transaction(
                job_id=job_id,
                txn_id=row['txn_id'] if pd.notna(row['txn_id']) else None,
                date=row['date'] if pd.notna(row['date']) else None,
                merchant=row['merchant'] if pd.notna(row['merchant']) else None,
                amount=float(row['amount']),
                currency=row['currency'],
                status=row['status'],
                category=row['category'],
                account_id=row['account_id'] if pd.notna(row['account_id']) else None,
                notes=row['notes'] if pd.notna(row['notes']) else None,
                is_anomaly=bool(row['is_anomaly']),
                anomaly_reason=row['anomaly_reason'] if row['anomaly_reason'] else None,
                llm_category=bool(row['llm_category']),
                llm_failed=bool(row['llm_failed']),
                llm_raw_response=row['llm_raw_response'] if row['llm_raw_response'] else None
            )
            db_transactions.append(txn)
            
        db.bulk_save_objects(db_transactions)
        db.commit()
        
        # 8. LLM Narrative Summary
        console.print(f"[job]JOB {job_id}[/job]: [info]Generating narrative summary...[/info]")
        # Compute financial summary stats
        # Total spend by currency
        inr_spend = float(df[df['currency'] == 'INR']['amount'].sum())
        usd_spend = float(df[df['currency'] == 'USD']['amount'].sum())
        
        # Top 3 merchants (grouped by merchant, summing amount)
        top_merchs = df.groupby('merchant')['amount'].sum().reset_index()
        top_merchs = top_merchs.sort_values(by='amount', ascending=False).head(3)
        top_merchants_list = []
        for _, r in top_merchs.iterrows():
            top_merchants_list.append({
                "merchant": str(r['merchant']),
                "spend": float(r['amount'])
            })
            
        anomaly_count = int(df['is_anomaly'].sum())
        
        summary_payload = {
            "total_spend_inr": inr_spend,
            "total_spend_usd": usd_spend,
            "top_merchants": top_merchants_list,
            "anomaly_count": anomaly_count
        }
        
        # Call LLM Narrative Summary
        summary_res = generate_narrative_summary(summary_payload)
        
        # Write Summary to Database
        job_summary = JobSummary(
            job_id=job_id,
            total_spend_inr=summary_res.get("total_spend_inr", inr_spend),
            total_spend_usd=summary_res.get("total_spend_usd", usd_spend),
            top_merchants=summary_res.get("top_merchants", top_merchants_list),
            anomaly_count=summary_res.get("anomaly_count", anomaly_count),
            narrative=summary_res.get("narrative", ""),
            risk_level=summary_res.get("risk_level", "low")
        )
        db.add(job_summary)
        
        # 9. Update job status to completed
        job.status = "completed"
        job.completed_at = datetime.datetime.utcnow()
        db.commit()
        
        console.print(f"[job]JOB {job_id}[/job]: [success]COMPLETED SUCCESSFULLY[/success]")
        
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        # Mark job as failed
        job.status = "failed"
        job.completed_at = datetime.datetime.utcnow()
        job.error_message = str(e)
        db.commit()
        console.print(f"[job]JOB {job_id}[/job]: [error]FAILED: {e}[/error]")
        
    finally:
        db.close()
