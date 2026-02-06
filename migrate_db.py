#!/usr/bin/env python3
"""
Database migration script for BP Badminton.
Run this script to sync database schema changes to PostgreSQL (Render) or SQLite.

Usage:
    # For local SQLite:
    python migrate_db.py

    # For PostgreSQL (Render):
    DATABASE_URL=postgresql://... python migrate_db.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

def get_database_url():
    """Get database URL, handling Render's postgres:// prefix"""
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url
    return 'sqlite:///instance/bpbadi.db'

def migrate_sqlite(db_path):
    """Run migrations for SQLite database"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Migrating SQLite database: {db_path}")

    # Check and add voting_frozen to sessions
    cursor.execute('PRAGMA table_info(sessions)')
    columns = [col[1] for col in cursor.fetchall()]

    if 'voting_frozen' not in columns:
        cursor.execute('ALTER TABLE sessions ADD COLUMN voting_frozen BOOLEAN DEFAULT 0')
        print("  - Added 'voting_frozen' column to sessions table")
    else:
        print("  - 'voting_frozen' column already exists in sessions table")

    # Check if birdie_bank table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='birdie_bank'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE birdie_bank (
                id INTEGER PRIMARY KEY,
                date DATETIME DEFAULT CURRENT_TIMESTAMP,
                transaction_type VARCHAR(20) NOT NULL,
                quantity INTEGER NOT NULL,
                cost FLOAT DEFAULT 0,
                notes TEXT,
                session_id INTEGER REFERENCES sessions(id),
                created_by INTEGER REFERENCES players(id),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER REFERENCES players(id),
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("  - Created 'birdie_bank' table")
    else:
        print("  - 'birdie_bank' table already exists")

    # Check if dropout_refunds table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dropout_refunds'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE dropout_refunds (
                id INTEGER PRIMARY KEY,
                player_id INTEGER NOT NULL REFERENCES players(id),
                session_id INTEGER NOT NULL REFERENCES sessions(id),
                refund_amount FLOAT NOT NULL DEFAULT 0,
                suggested_amount FLOAT DEFAULT 0,
                instructions TEXT,
                status VARCHAR(20) DEFAULT 'pending',
                processed_date DATETIME,
                created_by INTEGER REFERENCES players(id),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER REFERENCES players(id),
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("  - Created 'dropout_refunds' table")
    else:
        print("  - 'dropout_refunds' table already exists")

    conn.commit()
    conn.close()
    print("SQLite migration completed!")

def migrate_postgresql(database_url):
    """Run migrations for PostgreSQL database"""
    try:
        import psycopg2
    except ImportError:
        print("Error: psycopg2 is required for PostgreSQL migrations.")
        print("Install it with: pip install psycopg2-binary")
        sys.exit(1)

    print(f"Migrating PostgreSQL database...")

    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    # Check and add voting_frozen to sessions
    cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'sessions' AND column_name = 'voting_frozen'
    """)
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE sessions ADD COLUMN voting_frozen BOOLEAN DEFAULT FALSE')
        print("  - Added 'voting_frozen' column to sessions table")
    else:
        print("  - 'voting_frozen' column already exists in sessions table")

    # Check if birdie_bank table exists
    cursor.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'birdie_bank'
    """)
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE birdie_bank (
                id SERIAL PRIMARY KEY,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                transaction_type VARCHAR(20) NOT NULL,
                quantity INTEGER NOT NULL,
                cost FLOAT DEFAULT 0,
                notes TEXT,
                session_id INTEGER REFERENCES sessions(id),
                created_by INTEGER REFERENCES players(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER REFERENCES players(id),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("  - Created 'birdie_bank' table")
    else:
        print("  - 'birdie_bank' table already exists")

    # Check if dropout_refunds table exists
    cursor.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'dropout_refunds'
    """)
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE dropout_refunds (
                id SERIAL PRIMARY KEY,
                player_id INTEGER NOT NULL REFERENCES players(id),
                session_id INTEGER NOT NULL REFERENCES sessions(id),
                refund_amount FLOAT NOT NULL DEFAULT 0,
                suggested_amount FLOAT DEFAULT 0,
                instructions TEXT,
                status VARCHAR(20) DEFAULT 'pending',
                processed_date TIMESTAMP,
                created_by INTEGER REFERENCES players(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER REFERENCES players(id),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("  - Created 'dropout_refunds' table")
    else:
        print("  - 'dropout_refunds' table already exists")

    conn.commit()
    conn.close()
    print("PostgreSQL migration completed!")

def main():
    database_url = get_database_url()

    print("=" * 50)
    print("BP Badminton Database Migration")
    print("=" * 50)

    if database_url.startswith('sqlite'):
        # Extract path from sqlite:///path
        db_path = database_url.replace('sqlite:///', '')
        migrate_sqlite(db_path)
    elif database_url.startswith('postgresql'):
        migrate_postgresql(database_url)
    else:
        print(f"Unknown database type: {database_url}")
        sys.exit(1)

if __name__ == '__main__':
    main()
