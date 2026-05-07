"""Initialize database tables for first deployment."""
from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    # Drop all existing tables and recreate them
    db.drop_all()
    db.create_all()
    print("✓ Database tables dropped and recreated successfully")
