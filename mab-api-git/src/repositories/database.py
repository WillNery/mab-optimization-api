"""Snowflake database connection management."""

import time
from contextlib import contextmanager
from typing import Generator, Any

import snowflake.connector
from snowflake.connector import SnowflakeConnection

from src.config import settings
from src.logging_config import logger, log_db_query, log_error


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
    start_time = time.perf_counter()
    conn = None
    
    try:
        conn = snowflake.connector.connect(**get_connection_params())
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        logger.debug(
            "Snowflake connection established",
            extra={
                "type": "db_connection",
                "action": "connect",
                "duration_ms": round(duration_ms, 2),
            },
        )
        yield conn
        
    except Exception as e:
        log_error(
            message=f"Snowflake connection failed: {str(e)}",
            error_type=type(e).__name__,
        )
        raise
        
    finally:
        if conn:
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


def execute_query(
    query: str,
    params: dict | None = None,
    query_name: str = "unknown",
) -> list[dict]:
    """
    Execute a SELECT query and return results as list of dicts.
    
    Args:
        query: SQL query string
        params: Query parameters
        query_name: Name for logging purposes
        
    Returns:
        List of dictionaries with column names as keys
    """
    start_time = time.perf_counter()
    
    try:
        with get_cursor() as cursor:
            cursor.execute(query, params or {})
            columns = [col[0].lower() for col in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_db_query(
                query_name=query_name,
                duration_ms=duration_ms,
                rows_affected=len(results),
            )
            
            return results
            
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        log_error(
            message=f"Query failed: {query_name}",
            error_type=type(e).__name__,
            query_name=query_name,
            duration_ms=round(duration_ms, 2),
        )
        raise


def execute_write(
    query: str,
    params: dict | None = None,
    query_name: str = "unknown",
) -> int:
    """
    Execute an INSERT/UPDATE/DELETE query.
    
    Args:
        query: SQL query string
        params: Query parameters
        query_name: Name for logging purposes
        
    Returns:
        Number of rows affected
    """
    start_time = time.perf_counter()
    
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query, params or {})
                conn.commit()
                rows_affected = cursor.rowcount
                
                duration_ms = (time.perf_counter() - start_time) * 1000
                log_db_query(
                    query_name=query_name,
                    duration_ms=duration_ms,
                    rows_affected=rows_affected,
                )
                
                return rows_affected
            finally:
                cursor.close()
                
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        log_error(
            message=f"Write query failed: {query_name}",
            error_type=type(e).__name__,
            query_name=query_name,
            duration_ms=round(duration_ms, 2),
        )
        raise
