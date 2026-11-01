"""Shared test set-up: a throw-away database built from database/build.sql and the committed demo dataset."""
from __future__ import annotations

import os
import pathlib
import subprocess

import psycopg
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = os.environ.get("AMI_TEST_DB", "ami_apptest")
BASE_DSN = os.environ.get("AMI_TEST_ADMIN_DSN", "postgresql:///postgres")
DSN = os.environ.get("AMI_TEST_DSN", f"postgresql:///{DB}")


def _psql(*args):
    subprocess.run(["psql", "-q", "-v", "ON_ERROR_STOP=1", *args], check=True, cwd=ROOT, capture_output=True)


@pytest.fixture(scope="session", autouse=True)
def database():
    with psycopg.connect(BASE_DSN, autocommit=True) as c:
        c.execute(f"select pg_terminate_backend(pid) from pg_stat_activity where datname = '{DB}' and pid <> pg_backend_pid()")
        c.execute(f'drop database if exists "{DB}"')
        c.execute(f'create database "{DB}"')
    _psql("-d", DSN, "-f", "database/build.sql")
    _psql("-d", DSN, "-f", "seed/demo_dataset.sql")
    os.environ["DATABASE_URL"] = DSN
    yield DSN


