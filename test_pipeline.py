import time
import requests
import json
import os
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.theme import Theme
from rich import box

# Custom theme for a badass look
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red",
    "success": "green",
    "header": "bold magenta",
    "highlight": "bold cyan",
})

console = Console(theme=custom_theme)

API_URL = "http://localhost:8000"
CSV_FILE_PATH = "/home/swayam/Projects/ai-transaction-processing-pipeline/transactions.csv"

def run_test():
    console.clear()
    console.print(Panel.fit(
        "[header]AI-POWERED TRANSACTION PROCESSING PIPELINE[/header]\n"
        "[highlight]END-TO-END VALIDATION SUITE[/highlight]",
        box=box.DOUBLE,
        border_style="magenta",
        padding=(1, 2)
    ))

    if not os.path.exists(CSV_FILE_PATH):
        console.print(f"[error]Error:[/error] transactions.csv not found at {CSV_FILE_PATH}")
        return
        
    console.print(f"\n[info]1. INITIATING UPLOAD[/info]")
    console.print(f"Source: {CSV_FILE_PATH}")
    console.print(f"Target: {API_URL}/jobs/upload")

    try:
        with open(CSV_FILE_PATH, "rb") as f:
            files = {"file": (os.path.basename(CSV_FILE_PATH), f, "text/csv")}
            response = requests.post(f"{API_URL}/jobs/upload", files=files)
            
        if response.status_code != 202:
            console.print(f"[error]Upload failed:[/error] {response.status_code} - {response.text}")
            return
            
        upload_res = response.json()
        job_id = upload_res["job_id"]
        console.print(f"[success]Upload success![/success] Assigned Job ID: [highlight]{job_id}[/highlight]\n")
        
        # 2. Poll Status
        console.print(f"[info]2. MONITORING PIPELINE EXECUTION[/info]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task(description="Processing...", total=None)
            
            status = "pending"
            while status in ["pending", "processing"]:
                res = requests.get(f"{API_URL}/jobs/{job_id}/status")
                if res.status_code != 200:
                    console.print(f"[error]Failed to get job status:[/error] {res.status_code}")
                    return
                    
                status_res = res.json()
                status = status_res["status"]
                progress.update(task, description=f"Current Status: [highlight]{status.upper()}[/highlight]")
                
                if status in ["pending", "processing"]:
                    time.sleep(1.5)
        
        console.print(f"Pipeline finished with final status: [success]{status.upper()}[/success]\n")
        
        if status == "failed":
            res = requests.get(f"{API_URL}/jobs")
            jobs_list = res.json()
            for j in jobs_list:
                if j["id"] == job_id:
                    console.print(Panel(f"[error]Error Message:[/error]\n{j.get('error_message')}", title="Job Failure Details", border_style="red"))
            return
            
        # 3. Get results
        console.print(f"[info]3. RETRIEVING ANALYSIS RESULTS[/info]")
        res = requests.get(f"{API_URL}/jobs/{job_id}/results")
        if res.status_code != 200:
            console.print(f"[error]Failed to fetch results:[/error] {res.status_code}")
            return
            
        results = res.json()
        
        # Summary Table
        summary_table = Table(title="JOB EXECUTION SUMMARY", box=box.ROUNDED, border_style="cyan")
        summary_table.add_column("Metric", style="magenta")
        summary_table.add_column("Value", style="white")
        
        summary_table.add_row("Filename", results['filename'])
        summary_table.add_row("Status", f"[success]{results['status'].upper()}[/success]")
        summary_table.add_row("Raw Rows", str(results['row_count_raw']))
        summary_table.add_row("Clean Rows", str(results['row_count_clean']))
        summary_table.add_row("Created At", results['created_at'])
        summary_table.add_row("Completed At", results['completed_at'])
        
        console.print(summary_table)
        
        # Narrative Summary
        llm_sum = results.get("llm_summary")
        if llm_sum:
            risk_color = "green" if llm_sum['risk_level'].lower() == 'low' else "yellow" if llm_sum['risk_level'].lower() == 'medium' else "red"
            
            narrative_content = (
                f"[bold]Total Spend (INR):[/bold] {llm_sum['total_spend_inr']:.2f}\n"
                f"[bold]Total Spend (USD):[/bold] {llm_sum['total_spend_usd']:.2f}\n"
                f"[bold]Risk Level:[/bold] [{risk_color}]{llm_sum['risk_level'].upper()}[/{risk_color}]\n\n"
                f"[bold]Narrative:[/bold]\n{llm_sum['narrative']}"
            )
            console.print(Panel(narrative_content, title="[header]AI NARRATIVE INSIGHTS[/header]", border_style="magenta", box=box.ROUNDED))
            
            # Top Merchants
            merch_table = Table(title="TOP 3 MERCHANTS BY SPEND", box=box.SIMPLE, border_style="magenta")
            merch_table.add_column("Merchant", style="cyan")
            merch_table.add_column("Total Spend", style="white")
            for m in llm_sum['top_merchants']:
                merch_table.add_row(m['merchant'], f"{m['spend']:.2f}")
            console.print(merch_table)
            
        # Category Breakdown
        cat_table = Table(title="CATEGORY SPEND BREAKDOWN", box=box.ROUNDED, border_style="yellow")
        cat_table.add_column("Category", style="yellow")
        cat_table.add_column("Currency", style="cyan")
        cat_table.add_column("Total Amount", style="white", justify="right")
        
        breakdown = results["category_breakdown"]
        for curr, cats in breakdown.items():
            for cat, amount in cats.items():
                cat_table.add_row(cat, curr, f"{amount:.2f}")
        
        console.print(cat_table)
        
        # Anomalies
        anomalies = results['flagged_anomalies']
        anom_title = f"FLAGGED ANOMALIES ({len(anomalies)})"
        if anomalies:
            anom_table = Table(title=anom_title, box=box.HEAVY_EDGE, border_style="red")
            anom_table.add_column("ID", style="dim")
            anom_table.add_column("Account", style="cyan")
            anom_table.add_column("Merchant", style="magenta")
            anom_table.add_column("Amount", style="white")
            anom_table.add_column("Reason", style="red")
            
            for idx, anomaly in enumerate(anomalies[:10]): # Show top 10
                anom_table.add_row(
                    str(idx+1),
                    str(anomaly['account_id']),
                    anomaly['merchant'],
                    f"{anomaly['amount']} {anomaly['currency']}",
                    anomaly['anomaly_reason']
                )
            
            console.print(anom_table)
            if len(anomalies) > 10:
                console.print(f"[dim]... and {len(anomalies)-10} more anomalies.[/dim]")
        else:
            console.print(Panel("[success]No anomalies detected in this batch.[/success]", title=anom_title, border_style="green"))
            
        console.print(f"\n[success]Validation Suite Completed Successfully.[/success]")

    except Exception as e:
        console.print(f"[error]An unexpected error occurred:[/error] {str(e)}")
        import traceback
        console.print(traceback.format_exc())

if __name__ == "__main__":
    # Wait for service to be up if run immediately after docker compose
    # In a real scenario, we might want a more robust check
    time.sleep(2)
    run_test()
