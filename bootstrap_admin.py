#!/usr/bin/env python3
"""
Bootstrap Admin Script

Creates or updates the admin user from environment variables.
Idempotent - safe to run multiple times.

Usage:
    python bootstrap_admin.py

Environment Variables:
    ADMIN_EMAIL    - Admin email (default: admin@bahith.local)
    ADMIN_PASSWORD - Admin password (REQUIRED)
    ADMIN_NAME     - Admin display name (default: مسؤول النظام)
    DATABASE_URL   - Database connection string
"""
import os
import sys
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def get_admin_credentials():
    """
    Get admin credentials from environment variables.
    
    Returns:
        tuple: (email, password, name) or raises SystemExit if ADMIN_PASSWORD not set
    """
    from config import Config
    
    email = Config.ADMIN_EMAIL
    password = Config.ADMIN_PASSWORD
    name = Config.ADMIN_NAME
    
    if not password:
        logger.error("=" * 60)
        logger.error("ERROR: ADMIN_PASSWORD environment variable is required!")
        logger.error("")
        logger.error("Set it before running:")
        logger.error("  Windows:  set ADMIN_PASSWORD=your-secure-password")
        logger.error("  Linux:    export ADMIN_PASSWORD='your-secure-password'")
        logger.error("  .env:     ADMIN_PASSWORD=your-secure-password")
        logger.error("=" * 60)
        sys.exit(1)
    
    if len(password) < 8:
        logger.warning("Warning: ADMIN_PASSWORD is less than 8 characters (not recommended)")
    
    return email, password, name


def bootstrap_admin():
    """
    Create or update admin user.
    
    - If admin exists with same email: updates password and name
    - If user exists but not admin: promotes to admin
    - If no user exists: creates new admin
    
    Returns:
        User: The admin user instance
    """
    email, password, name = get_admin_credentials()
    
    # Import Flask app and models
    from app import app
    from models import db, User
    
    with app.app_context():
        # Ensure tables exist
        db.create_all()
        
        logger.info("=" * 60)
        logger.info("Bootstrap Admin")
        logger.info("=" * 60)
        logger.info(f"Email: {email}")
        logger.info(f"Name: {name}")
        logger.info("")
        
        # Check for existing user
        existing = User.query.filter_by(email=email).first()
        
        if existing:
            if existing.is_admin:
                # Admin already exists - update password if changed
                logger.info("Admin user already exists")
                
                if not existing.check_password(password):
                    existing.set_password(password)
                    logger.info("Password updated")
                
                if existing.display_name != name:
                    existing.display_name = name
                    logger.info("Display name updated")
                
                db.session.commit()
                logger.info("Admin verified successfully")
            else:
                # User exists but not admin - promote
                logger.info(f"User exists, promoting to admin: {email}")
                existing.is_admin = True
                existing.is_active = True
                existing.set_password(password)
                existing.display_name = name
                db.session.commit()
                logger.info("User promoted to admin successfully")
            
            admin = existing
        else:
            # Create new admin
            logger.info("Creating new admin user...")
            
            admin = User(
                email=email,
                display_name=name,
                is_admin=True,
                is_active=True
            )
            admin.set_password(password)
            
            db.session.add(admin)
            db.session.commit()
            
            logger.info("Admin user created successfully!")
        
        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("Admin Bootstrap Complete")
        logger.info(f"  ID: {admin.id}")
        logger.info(f"  Email: {admin.email}")
        logger.info(f"  Name: {admin.display_name}")
        logger.info(f"  Admin: {admin.is_admin}")
        logger.info(f"  Active: {admin.is_active}")
        logger.info("=" * 60)
        
        return admin


def list_admins():
    """List all admin users in the database."""
    from app import app
    from models import db, User
    
    with app.app_context():
        admins = User.query.filter_by(is_admin=True).all()
        
        logger.info("=" * 60)
        logger.info(f"Admin Users ({len(admins)} total)")
        logger.info("=" * 60)
        
        for admin in admins:
            logger.info(f"  - {admin.email} | {admin.display_name} | Active: {admin.is_active}")
        
        if not admins:
            logger.info("  (No admin users found)")
        
        logger.info("=" * 60)
        return admins


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Bootstrap admin user')
    parser.add_argument('--list', action='store_true', help='List all admin users')
    args = parser.parse_args()
    
    if args.list:
        list_admins()
    else:
        bootstrap_admin()
