"""Create instance directory for SQLite database."""
from pathlib import Path

# Create instance directory if it doesn't exist
instance_dir = Path(__file__).parent / "instance"
instance_dir.mkdir(exist_ok=True)
print(f"✓ Instance directory created: {instance_dir}")
