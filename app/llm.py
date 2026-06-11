import json
import time
import random
import requests
from typing import List, Dict, Any
from app.config import GEMINI_API_KEY

def call_gemini_api_with_retry(prompt: str, system_instruction: str = None) -> str:
    """
    Calls the Gemini 1.5 Flash API with exponential backoff up to 3 retries (4 attempts total).
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }

    headers = {"Content-Type": "application/json"}
    
    last_err = None
    for attempt in range(4): # 0, 1, 2, 3
        if attempt > 0:
            sleep_time = (2 ** attempt) + random.uniform(0.1, 1.0)
            time.sleep(sleep_time)
            
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                res_data = response.json()
                text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                return text
            else:
                raise Exception(f"HTTP Status {response.status_code}: {response.text}")
        except Exception as e:
            last_err = e
            print(f"Gemini API call attempt {attempt + 1} failed: {e}")
            
    raise last_err


def rule_based_fallback_categorization(transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Rule-based transaction categorization as a smart fallback if the Gemini API key is missing or fails.
    """
    results = []
    for tx in transactions:
        merchant = str(tx.get("merchant", "")).lower()
        notes = str(tx.get("notes", "")).lower()
        tx_id = tx.get("id")
        
        # Smart categorization rules
        if any(x in merchant for x in ["swiggy", "zomato", "restaurant", "food", "cafe", "diner"]):
            cat = "Food"
        elif any(x in merchant for x in ["amazon", "flipkart", "myntra", "shop", "mart", "store"]):
            cat = "Shopping"
        elif any(x in merchant for x in ["irctc", "makemytrip", "travel", "flight", "airway", "railway", "hotel", "expedia"]):
            cat = "Travel"
        elif any(x in merchant for x in ["ola", "uber", "cab", "transport", "metro", "bus", "taxi"]):
            cat = "Transport"
        elif any(x in merchant for x in ["jio", "airtel", "recharge", "electric", "power", "bill", "utilities", "water"]):
            cat = "Utilities"
        elif any(x in merchant for x in ["atm", "hdfc", "sbi", "icici", "cash", "withdrawal"]):
            cat = "Cash Withdrawal"
        elif any(x in merchant for x in ["bookmyshow", "netflix", "movie", "cinema", "entertainment", "theatre", "show"]):
            cat = "Entertainment"
        else:
            cat = "Other"
            
        results.append({
            "id": tx_id,
            "category": cat
        })
    return results


def rule_based_fallback_summary(summary_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rule-based narrative summary as a fallback if the Gemini API key is missing or fails.
    """
    inr_total = summary_data.get("total_spend_inr", 0.0)
    usd_total = summary_data.get("total_spend_usd", 0.0)
    anomaly_count = summary_data.get("anomaly_count", 0)
    top_merchants_list = summary_data.get("top_merchants", [])
    
    top_merchants_str = ", ".join([f"{item['merchant']} ({item['spend']:.2f})" for item in top_merchants_list[:3]])
    
    # Simple risk level logic
    if anomaly_count == 0:
        risk_level = "low"
    elif anomaly_count <= 2:
        risk_level = "medium"
    else:
        risk_level = "high"
        
    narrative = (
        f"The transaction processing job has completed successfully. A total of {inr_total:.2f} INR "
        f"and {usd_total:.2f} USD was processed. The top merchants by spending volume are {top_merchants_str}. "
        f"We identified {anomaly_count} statistical and merchant-currency location anomalies, representing a {risk_level} overall risk level."
    )
    
    return {
        "total_spend_inr": inr_total,
        "total_spend_usd": usd_total,
        "top_merchants": top_merchants_list,
        "anomaly_count": anomaly_count,
        "narrative": narrative,
        "risk_level": risk_level
    }


def classify_transactions_batch(transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Categorizes a batch of transactions. Attempts Gemini 1.5 Flash if API key is set;
    falls back to rule-based classification if it fails or is not configured.
    """
    if not transactions:
        return []
        
    # If no api key, fallback to rule-based categorization immediately
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY is not set. Falling back to rule-based categorization.")
        return rule_based_fallback_categorization(transactions)

    system_instruction = (
        "You are a precise transaction categorization assistant. Categorize each transaction into "
        "exactly one of the following categories: Food, Shopping, Travel, Transport, Utilities, "
        "Cash Withdrawal, Entertainment, or Other. Do not invent other categories."
    )
    
    prompt = (
        "Classify the following list of transactions. Return a JSON object with a single key "
        "'categorized_transactions', which maps to a list of objects, each having the keys "
        "'id' and 'category'. Do not return any other text, markdown formatting other than JSON, "
        "or explanations.\n\n"
        f"Transactions: {json.dumps(transactions)}"
    )

    try:
        response_text = call_gemini_api_with_retry(prompt, system_instruction)
        # Clean response if it contains markdown formatting
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()
        
        data = json.loads(cleaned_text)
        return data.get("categorized_transactions", [])
    except Exception as e:
        print(f"Gemini categorization batch failed: {e}. Falling back to rule-based classification.")
        # Rule-based fallback as per requirement 5.e ("If all retries fail, mark that batch as llm_failed and continue - do not fail the entire job")
        # In this helper, we return the fallback classifications, and the calling task will mark llm_failed = True.
        fallback_res = rule_based_fallback_categorization(transactions)
        # Mark all of them as having failed the LLM call
        for res in fallback_res:
            res["llm_failed"] = True
        return fallback_res


def generate_narrative_summary(summary_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates a narrative summary of all transactions in the job.
    """
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY is not set. Falling back to rule-based summary.")
        return rule_based_fallback_summary(summary_data)

    system_instruction = (
        "You are a financial summary analyst. Given the financial statistics, generate a JSON summary "
        "complying with the requested keys and format."
    )
    
    prompt = (
        "Generate a financial summary narrative and risk assessment for the transaction batch based on the "
        "following raw statistics. Return a JSON object with the exact keys: "
        "'total_spend_inr', 'total_spend_usd', 'top_merchants', 'anomaly_count', 'narrative', 'risk_level'.\n"
        "- 'narrative' must be a concise 2-3 sentence overview explaining spending trends.\n"
        "- 'risk_level' must be 'low', 'medium', or 'high'.\n"
        "- 'top_merchants' should list the top 3 merchants with their spend amounts as a list of dicts: "
        "[{\"merchant\": \"Name\", \"spend\": amount}].\n\n"
        f"Raw Statistics: {json.dumps(summary_data)}\n\n"
        "Return ONLY the raw JSON object."
    )
    
    try:
        response_text = call_gemini_api_with_retry(prompt, system_instruction)
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()
        
        data = json.loads(cleaned_text)
        return {
            "total_spend_inr": data.get("total_spend_inr", summary_data.get("total_spend_inr", 0.0)),
            "total_spend_usd": data.get("total_spend_usd", summary_data.get("total_spend_usd", 0.0)),
            "top_merchants": data.get("top_merchants", summary_data.get("top_merchants", [])),
            "anomaly_count": data.get("anomaly_count", summary_data.get("anomaly_count", 0)),
            "narrative": data.get("narrative", ""),
            "risk_level": data.get("risk_level", "low")
        }
    except Exception as e:
        print(f"Gemini narrative generation failed: {e}. Falling back to rule-based summary.")
        return rule_based_fallback_summary(summary_data)
