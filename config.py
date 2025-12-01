"""
Configuration for Flask application
"""
import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # Database
    # Use /tmp for SQLite on Railway (always writable), instance folder locally
    if os.environ.get('RAILWAY_ENVIRONMENT'):
        db_path = os.path.join('/tmp', 'pettycash.db')
    else:
        db_path = os.path.join(basedir, 'instance', 'pettycash.db')

    # Get database URL and configure for psycopg3
    database_url = os.environ.get('DATABASE_URL') or f'sqlite:///{db_path}'

    # Railway provides postgresql:// but we need postgresql+psycopg:// for psycopg3
    if database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)

    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

    # File uploads (signatures)
    # Use Railway volume for persistent storage, local folder for development
    if os.environ.get('RAILWAY_ENVIRONMENT'):
        UPLOAD_FOLDER = '/data/signatures'
    else:
        UPLOAD_FOLDER = os.path.join(basedir, 'static', 'signatures')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max file size
