from __future__ import annotations

import os

DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5433/taskrunner"
DEFAULT_CDRMIND_URL = "http://cdrmind:8000"


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_cdrmind_url() -> str:
    return os.getenv("CDRMIND_URL", DEFAULT_CDRMIND_URL)
