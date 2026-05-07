"""Initialize database tables for first deployment."""
from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    # Create all tables
    db.create_all()
    print("✓ Database tables created successfully")
