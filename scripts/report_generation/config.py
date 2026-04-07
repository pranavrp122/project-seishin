"""Paths and defaults for the report generation pipeline."""
import os

# Match nexus_engine defaults; override with env when not using Docker bridge.
BRAIN_URL = os.environ.get("NEXUS_BRAIN_URL", "http://172.17.0.1:8001/v1/completions")
MODEL_NAME = os.environ.get("NEXUS_MODEL_NAME", "Qwen/Qwen3.5-9B")

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("REPORT_GEN_DATA_DIR", os.path.join(_PACKAGE_DIR, "data"))
WAREHOUSE_DB_PATH = os.path.join(DATA_DIR, "warehouse.db")

MAX_SQL_ROWS = int(os.environ.get("REPORT_MAX_SQL_ROWS", "500"))
SQL_LLM_MAX_TOKENS = int(os.environ.get("REPORT_SQL_MAX_TOKENS", "512"))
UNDERSTAND_MAX_TOKENS = int(os.environ.get("REPORT_UNDERSTAND_MAX_TOKENS", "400"))
SUMMARY_MAX_TOKENS = int(os.environ.get("REPORT_SUMMARY_MAX_TOKENS", "200"))

# Analytic tables only; metadata (report_jobs) must never appear in user/LLM SQL.
ALLOWED_SQL_TABLES = frozenset({"orders", "customers"})
