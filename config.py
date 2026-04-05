"""
Application Configuration

Loads settings from environment variables with sensible defaults.
DATABASE_URL is required for production.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration"""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Database
    DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///bahith.db')
    
    # Fix Render.com's postgres:// → postgresql://
    if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    # Security
    BCRYPT_LOG_ROUNDS = 12
    JWT_EXPIRATION_DAYS = 7
    
    # Admin Bootstrap (from environment)
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@bahith.local')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')  # Required for bootstrap
    ADMIN_NAME = os.environ.get('ADMIN_NAME', 'مسؤول النظام')
    
    # API Keys (existing)
    IMGBB_API_KEY = os.environ.get('IMGBB_API_KEY')
    AIORNOT_API_KEY = os.environ.get('AIORNOT_API_KEY')
    SERPAPI_API_KEY = os.environ.get('SERPAPI_API_KEY')
    ZENSERP_API_KEY = os.environ.get('ZENSERP_API_KEY')


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SQLALCHEMY_ECHO = False
    
    # Stricter security in production
    BCRYPT_LOG_ROUNDS = 14


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


# Config selector
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config():
    """Get configuration based on FLASK_ENV"""
    env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default'])
