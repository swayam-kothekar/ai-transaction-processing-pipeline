import time
import requests
import json
import os
import re

API_URL = "http://localhost:8000"
CSV_FILE_PATH = "/home/swayam/Projects/ai-transaction-processing-pipeline/transactions.csv"

def clean_markup(text):
    return re.sub(r"\[/?([a-zA-Z0-9_\.\s/-]*)\]", "", str(text))

def cprint(text):
    print(clean_markup(text))

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_panel(content, title=None, double=False):
    content = clean_markup(content)
    lines = content.splitlines()
    max_len = max(len(line) for line in lines) if lines else 0
    inner_w = max_len + 4
    if title:
        inner_w = max(inner_w, len(clean_markup(title)) + 6)
    
    tl, tr, bl, br, hz, vt = ("╔", "╗", "╚", "╝", "═", "║") if double else ("╭", "╮", "╰", "╯", "─", "│")
    
    if title:
        clean_title = clean_markup(title)
        title_formatted = f" {clean_title} "
        rem = inner_w - len(title_formatted)
        left_len = rem // 2
        right_len = rem - left_len
        print(f"{tl}{hz * left_len}{title_formatted}{hz * right_len}{tr}")
    else:
        print(f"{tl}{hz * inner_w}{tr}")
        
    for line in lines:
        padding = inner_w - len(line)
        print(f"{vt}  {line}{' ' * (padding - 2)}  {vt}")
        
    print(f"{bl}{hz * inner_w}{br}")

def print_table(title, headers, rows, alignments=None, border="rounded"):
    clean_headers = [clean_markup(h) for h in headers]
    clean_rows = [[clean_markup(cell) for cell in row] for row in rows]
    
    col_widths = []
    for i in range(len(headers)):
        max_w = len(clean_headers[i])
        for row in clean_rows:
            if i < len(row):
                max_w = max(max_w, len(row[i]))
        col_widths.append(max_w)
        
    if border == "double":
        tl, tm, tr, ml, mm, mr, bl, bm, br, hz, vt = "╔", "╦", "╗", "╠", "╬", "╣", "╚", "╩", "╝", "═", "║"
    elif border == "heavy":
        tl, tm, tr, ml, mm, mr, bl, bm, br, hz, vt = "┏", "┳", "┓", "┣", "╋", "┫", "┗", "┻", "┛", "━", "┃"
    elif border == "simple":
        tl, tm, tr, ml, mm, mr, bl, bm, br, hz, vt = " ", " ", " ", " ", " ", " ", " ", " ", " ", "─", " "
    else:
        tl, tm, tr, ml, mm, mr, bl, bm, br, hz, vt = "╭", "┬", "╮", "├", "┼", "┤", "╰", "┴", "╯", "─", "│"
        
    def make_separator(l_char, m_char, r_char):
        if not tl.strip() and not hz.strip():
            parts = [hz * (w + 2) for w in col_widths]
            return " " + hz.join(parts) + " "
        parts = [hz * (w + 2) for w in col_widths]
        return l_char + m_char.join(parts) + r_char
        
    def print_row_line(row_cells):
        parts = []
        for i, cell in enumerate(row_cells):
            w = col_widths[i]
            align = alignments[i] if alignments and i < len(alignments) else "left"
            if align == "right":
                padded = cell.rjust(w)
            elif align == "center":
                padded = cell.center(w)
            else:
                padded = cell.ljust(w)
            parts.append(f" {padded} ")
        if not vt.strip():
            return " " + " ".join(parts) + " "
        return vt + vt.join(parts) + vt
        
    table_width = sum(col_widths) + 3 * len(headers) - 1
    if vt.strip():
        table_width += 2
    if title:
        print(f"{clean_markup(title).center(table_width)}")
        
    if tl.strip() or hz.strip():
        print(make_separator(tl, tm, tr))
        
    print(print_row_line(clean_headers))
    
    if ml.strip() or hz.strip():
        print(make_separator(ml, mm, mr))
        
    for row in clean_rows:
        print(print_row_line(row))
        
    if bl.strip() or hz.strip():
        print(make_separator(bl, bm, br))

def run_test():
    clear_screen()
    print_panel(
        "AI-POWERED TRANSACTION PROCESSING PIPELINE\n"
        "END-TO-END VALIDATION SUITE",
        double=True
    )

    if not os.path.exists(CSV_FILE_PATH):
        cprint(f"[error]Error:[/error] transactions.csv not found at {CSV_FILE_PATH}")
        return
        
    cprint(f"\n[info]1. INITIATING UPLOAD[/info]")
    cprint(f"Source: {CSV_FILE_PATH}")
    cprint(f"Target: {API_URL}/jobs/upload")

    try:
        with open(CSV_FILE_PATH, "rb") as f:
            files = {"file": (os.path.basename(CSV_FILE_PATH), f, "text/csv")}
            response = requests.post(f"{API_URL}/jobs/upload", files=files)
            
        if response.status_code != 202:
            cprint(f"[error]Upload failed:[/error] {response.status_code} - {response.text}")
            return
            
        upload_res = response.json()
        job_id = upload_res["job_id"]
        cprint(f"[success]Upload success![/success] Assigned Job ID: [highlight]{job_id}[/highlight]\n")
        
        # 2. Poll Status
        cprint(f"[info]2. MONITORING PIPELINE EXECUTION[/info]")
        
        status = "pending"
        last_printed_status = None
        while status in ["pending", "processing"]:
            res = requests.get(f"{API_URL}/jobs/{job_id}/status")
            if res.status_code != 200:
                cprint(f"[error]Failed to get job status:[/error] {res.status_code}")
                return
                
            status_res = res.json()
            status = status_res["status"]
            if status != last_printed_status:
                cprint(f"Current Status: [highlight]{status.upper()}[/highlight]")
                last_printed_status = status
            
            if status in ["pending", "processing"]:
                time.sleep(1.5)
        
        cprint(f"Pipeline finished with final status: [success]{status.upper()}[/success]\n")
        
        if status == "failed":
            res = requests.get(f"{API_URL}/jobs")
            jobs_list = res.json()
            for j in jobs_list:
                if j["id"] == job_id:
                    print_panel(f"Error Message:\n{j.get('error_message')}", title="Job Failure Details")
            return
            
        # 3. Get results
        cprint(f"[info]3. RETRIEVING ANALYSIS RESULTS[/info]")
        res = requests.get(f"{API_URL}/jobs/{job_id}/results")
        if res.status_code != 200:
            cprint(f"[error]Failed to fetch results:[/error] {res.status_code}")
            return
            
        results = res.json()
        
        # Summary Table
        summary_rows = [
            ["Filename", results['filename']],
            ["Status", results['status'].upper()],
            ["Raw Rows", str(results['row_count_raw'])],
            ["Clean Rows", str(results['row_count_clean'])],
            ["Created At", results['created_at']],
            ["Completed At", results['completed_at']],
        ]
        print_table("JOB EXECUTION SUMMARY", ["Metric", "Value"], summary_rows, border="rounded")
        
        # Narrative Summary
        llm_sum = results.get("llm_summary")
        if llm_sum:
            narrative_content = (
                f"Total Spend (INR): {llm_sum['total_spend_inr']:.2f}\n"
                f"Total Spend (USD): {llm_sum['total_spend_usd']:.2f}\n"
                f"Risk Level: {llm_sum['risk_level'].upper()}\n\n"
                f"Narrative:\n{llm_sum['narrative']}"
            )
            print_panel(narrative_content, title="AI NARRATIVE INSIGHTS")
            
            # Top Merchants
            merch_rows = []
            for m in llm_sum['top_merchants']:
                merch_rows.append([m['merchant'], f"{m['spend']:.2f}"])
            print_table("TOP 3 MERCHANTS BY SPEND", ["Merchant", "Total Spend"], merch_rows, border="simple")
            
        # Category Breakdown
        cat_rows = []
        breakdown = results["category_breakdown"]
        for curr, cats in breakdown.items():
            for cat, amount in cats.items():
                cat_rows.append([cat, curr, f"{amount:.2f}"])
        print_table("CATEGORY SPEND BREAKDOWN", ["Category", "Currency", "Total Amount"], cat_rows, alignments=["left", "left", "right"], border="rounded")
        
        # Anomalies
        anomalies = results['flagged_anomalies']
        anom_title = f"FLAGGED ANOMALIES ({len(anomalies)})"
        if anomalies:
            anom_rows = []
            for idx, anomaly in enumerate(anomalies[:10]):
                anom_rows.append([
                    str(idx+1),
                    str(anomaly['account_id']),
                    anomaly['merchant'],
                    f"{anomaly['amount']} {anomaly['currency']}",
                    anomaly['anomaly_reason']
                ])
            print_table(anom_title, ["ID", "Account", "Merchant", "Amount", "Reason"], anom_rows, border="heavy")
            if len(anomalies) > 10:
                cprint(f"[dim]... and {len(anomalies)-10} more anomalies.[/dim]")
        else:
            print_panel("No anomalies detected in this batch.", title=anom_title)
            
        cprint(f"\n[success]Validation Suite Completed Successfully.[/success]")

    except Exception as e:
        cprint(f"[error]An unexpected error occurred:[/error] {str(e)}")
        import traceback
        cprint(traceback.format_exc())

if __name__ == "__main__":
    time.sleep(2)
    run_test()
