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
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'pettycash.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

    # File uploads (signatures)
    UPLOAD_FOLDER = os.path.join(basedir, 'static', 'signatures')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max file size
