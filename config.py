import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///bpbadi.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    APP_PASSWORD = os.environ.get('APP_PASSWORD') or 'bpbadi2024'
