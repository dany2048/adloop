"""Central config. Loads .env once and exposes endpoints + model names."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
OPENAI_BASE_URL = os.getenv(
    "DASHSCOPE_OPENAI_BASE_URL",
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
)
HTTP_BASE_URL = os.getenv(
    "DASHSCOPE_HTTP_BASE_URL",
    "https://dashscope-intl.aliyuncs.com/api/v1",
)

TEXT_MODEL = os.getenv("QWEN_TEXT_MODEL", "qwen-plus")
PLAN_MODEL = os.getenv("QWEN_PLAN_MODEL", "qwen-max")
VL_MODEL = os.getenv("QWEN_VL_MODEL", "qwen-vl-max")
WANX_T2I_MODEL = os.getenv("WANX_T2I_MODEL", "wan2.2-t2i-flash")
EMBED_MODEL = os.getenv("QWEN_EMBED_MODEL", "text-embedding-v3")

# Apify (live Pinterest reference scraping for the Design Researcher; optional).
APIFY_API_KEY = os.getenv("APIFY_API_KEY", "")
PINTEREST_ACTOR = os.getenv("PINTEREST_ACTOR", "fatihtahta~pinterest-scraper-search")

# Where the SQLite memory store lives.
DB_PATH = os.getenv("ADLOOP_DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "adloop.db"))


def require_key() -> str:
    if not DASHSCOPE_API_KEY:
        raise RuntimeError(
            "DASHSCOPE_API_KEY is not set. Copy .env.example to .env and paste your key."
        )
    return DASHSCOPE_API_KEY
