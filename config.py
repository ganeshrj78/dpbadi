import os
from dotenv import load_dotenv

load_dotenv()

def get_database_url():
    """Get database URL, handling Render's postgres:// prefix"""
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # Render uses postgres:// but SQLAlchemy requires postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url
    # Default to SQLite for local development
    return 'sqlite:///bpbadi.db'

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    APP_PASSWORD = os.environ.get('APP_PASSWORD') or 'bpbadi2024'

    # Environment detection
    IS_PRODUCTION = os.environ.get('RENDER') == 'true'
