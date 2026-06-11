import os
from dotenv import load_dotenv

# Load env variables from .env file
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/transactions_db")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
