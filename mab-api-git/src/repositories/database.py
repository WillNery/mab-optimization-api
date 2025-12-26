"""Snowflake database connection management."""

from contextlib import contextmanager
from typing import Generator, Any

import snowflake.connector
from snowflake.connector import SnowflakeConnection

from src.config import settings


def get_connection_params() -> dict[str, str]:
    """Get Snowflake connection parameters from settings."""
    return {
        "account": settings.snowflake_account,
        "user": settings.snowflake_user,
        "password": settings.snowflake_password,
        "warehouse": settings.snowflake_warehouse,
        "database": settings.snowflake_database,
        "schema": settings.snowflake_schema,
    }


@contextmanager
def get_connection() -> Generator[SnowflakeConnection, None, None]:
    """
    Context manager for Snowflake connections.
    
    Usage:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
    """
    conn = snowflake.connector.connect(**get_connection_params())
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor() -> Generator[Any, None, None]:
    """
    Context manager for Snowflake cursors.
    
    Usage:
        with get_cursor() as cursor:
            cursor.execute("SELECT 1")
            results = cursor.fetchall()
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()


def execute_query(query: str, params: dict | None = None) -> list[dict]:
    """
    Execute a SELECT query and return results as list of dicts.
    
    Args:
        query: SQL query string
        params: Query parameters
        
    Returns:
        List of dictionaries with column names as keys
    """
    with get_cursor() as cursor:
        cursor.execute(query, params or {})
        columns = [col[0].lower() for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def execute_write(query: str, params: dict | None = None) -> int:
    """
    Execute an INSERT/UPDATE/DELETE query.
    
    Args:
        query: SQL query string
        params: Query parameters
        
    Returns:
        Number of rows affected
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(query, params or {})
            conn.commit()
            return cursor.rowcount
        finally:
            cursor.close()
