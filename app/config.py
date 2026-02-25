import os
from dotenv import load_dotenv

load_dotenv()

# Required — fails fast if missing
API_KEY: str = os.environ["API_KEY"]

APP_ENV: str = os.getenv("APP_ENV", "development")
PORT: int = int(os.getenv("PORT", "8000"))
CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "")


def is_production() -> bool:
    return APP_ENV == "production"


def get_cors_origins() -> list[str]:
    if not CORS_ORIGINS:
        return []
    return [origin.strip() for origin in CORS_ORIGINS.split(",") if origin.strip()]
