"""
Configuration for Flask application
"""
import os
from datetime import timedelta
from dotenv import load_dotenv
from sqlalchemy.pool import NullPool

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Secure cookies in production
    SESSION_COOKIE_SECURE = bool(os.environ.get('PRODUCTION'))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Database - SQLite
    # Docker: /app/data/pettycash.db (persistent volume)
    # Local dev: instance/pettycash.db
    DATA_DIR = os.environ.get('DATA_DIR', os.path.join(basedir, 'instance'))
    database_url = os.environ.get('DATABASE_URL', f'sqlite:///{os.path.join(DATA_DIR, "pettycash.db")}')

    # Normalize postgresql:// to postgresql+psycopg:// for psycopg3
    if database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)

    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # SQLite needs NullPool (no connection pooling) to avoid "database is locked" errors
    # PostgreSQL can use standard pooling
    if database_url.startswith('sqlite'):
        SQLALCHEMY_ENGINE_OPTIONS = {
            'poolclass': NullPool,
            'connect_args': {'timeout': 15, 'check_same_thread': False},
        }
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_size': 5,
            'max_overflow': 10,
        }

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

    # File uploads (signatures)
    # Docker: /app/data/signatures (persistent volume)
    # Local dev: static/signatures
    UPLOAD_FOLDER = os.environ.get('UPLOAD_DIR', os.path.join(basedir, 'static', 'signatures'))
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max file size
