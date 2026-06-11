# AI-Powered Transaction Processing Pipeline

An asynchronous backend pipeline that ingests dirty financial transaction CSV files, cleans the data, performs statistical and merchant-currency location anomaly detection, uses LLM classification (Google Gemini 1.5 Flash) to categorize and summarize the data, and stores the results in PostgreSQL.

## 🚀 Key Features
- **API Framework**: FastAPI with Pydantic v2 schemas.
- **Asynchronous Processing**: Celery task queue with Redis broker.
- **Database**: PostgreSQL (SQLAlchemy ORM) with automatic tables initialization.
- **Smart Data Cleaning**: Normalizes dates to ISO 8601, cleans currency formats/symbols, drops duplicate records, and fills missing categories.
- **Statistical Outlier Detection**: Flags transactions where the amount is greater than 3x the median of the respective account.
- **Domestic-USD Anomaly Checking**: Flags transactions in USD made with domestic brands (e.g. Swiggy, Ola, IRCTC).
- **Gemini LLM Integration**: Uses Gemini 1.5 Flash for batch categorization of uncategorized transactions and narrative generation with exponential backoff retries.
- **Fail-Safe Fallbacks**: Uses a rule-based engine when `GEMINI_API_KEY` is not present or if all retries fail, ensuring 100% processing success.
- **Single-Command Startup**: Fully containerized using Docker and Docker Compose with dependencies checking.

---

## 🛠️ Tech Stack
- **FastAPI** (Python 3.10)
- **Celery** (with Redis)
- **PostgreSQL**
- **Pandas** (for performant data manipulation and statistics)
- **Docker & Docker Compose**

---

## 📂 Project Structure
```
/home/swayam/Projects/ai-transaction-processing-pipeline/
├── app/
│   ├── __init__.py
│   ├── config.py          # Environment settings
│   ├── database.py        # SQLAlchemy engine & sessionmaker
│   ├── models.py          # SQLAlchemy PostgreSQL schemas
│   ├── schemas.py         # Pydantic validation/response schemas
│   ├── celery_app.py      # Celery app initialization
│   ├── tasks.py           # Core async cleaning & processing pipeline
│   ├── llm.py             # Gemini API wrapper with fail-safe fallback
│   └── main.py            # FastAPI main router & endpoints
├── Dockerfile             # Multi-purpose container image
├── docker-compose.yml     # Complete stack configuration
├── requirements.txt       # Dependencies
├── .env                   # Active environment variables
├── .env.example           # Example configuration
├── transactions.csv       # Dataset provided
├── test_pipeline.py       # End-to-end automation test script
└── README.md              # Project documentation
```

---

## ⚙️ Quick Start

### Prerequisites
Make sure you have [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed.

### 1. Configure the Environment
Copy the example environment file or edit the existing `.env` file in the root directory:
```bash
cp .env.example .env
```
To enable actual Google Gemini 1.5 Flash API analysis, insert your API key:
```env
GEMINI_API_KEY=your_google_gemini_api_key_here
```
*Note: If no API key is supplied, the application automatically uses a smart rule-based rule set to classify transactions and generate narratives, ensuring the pipeline completes without errors.*

### 2. Start the Pipeline
Run the following command to build and start PostgreSQL, Redis, FastAPI, and Celery:
```bash
docker compose up --build
```
This single command spins up all services, initializes the database tables, and exposes the FastAPI app at [http://localhost:8000](http://localhost:8000).

---

## 📡 API Reference

- **Interactive API Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Endpoints
1. **`POST /jobs/upload`**
   - Uploads the transaction CSV.
   - Response: `{"job_id": "<uuid>", "filename": "transactions.csv", "status": "pending", "message": "..."}`
   
2. **`GET /jobs/{job_id}/status`**
   - Returns the status of the job (`pending`, `processing`, `completed`, `failed`).
   - If completed, includes high-level statistics: `total_spend_inr`, `total_spend_usd`, `anomaly_count`, and `risk_level`.

3. **`GET /jobs/{job_id}/results`**
   - Returns the complete result set:
     - Cleaned transactions list
     - Flagged anomalies list
     - Aggregate spend by category and currency (per-category spend breakdown)
     - LLM-generated narrative summary and risk assessment

4. **`GET /jobs`**
   - Lists all jobs with basic details. Supports status filtering (e.g. `/jobs?status=completed`).

---

## 🧪 Testing the Pipeline
An automated Python test script is included in the workspace to verify everything end-to-end.

Ensure the containers are running, then execute:
```bash
python3 test_pipeline.py
```
This script will upload `transactions.csv`, track the status updates from `pending` -> `processing` -> `completed`, and print the complete results directly to your console.
