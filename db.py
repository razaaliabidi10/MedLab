import mysql.connector
from flask import current_app


def get_db_connection():
    """Return a fresh MySQL connection using app config."""
    cfg = current_app.config
    return mysql.connector.connect(
        host=cfg["DB_HOST"],
        port=cfg["DB_PORT"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        database=cfg["DB_NAME"],
        autocommit=False,
    )


def query_db(sql, params=(), one=False):
    """Run a SELECT and return list of dicts (or a single dict if one=True)."""
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows[0] if (one and rows) else (None if one else rows)


def execute_db(sql, params=()):
    """Run INSERT / UPDATE / DELETE inside a transaction; return lastrowid."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    last_id = cur.lastrowid
    cur.close()
    conn.close()
    return last_id
