"""
Database migration script to add employee_name column
Run this once to update the database schema
"""
from app import app, db

with app.app_context():
    print("🔄 Dropping all tables...")
    db.drop_all()

    print("✨ Creating tables with new schema...")
    db.create_all()

    print("✅ Database migration complete!")
    print("Note: All existing data has been cleared.")
