"""
EXAMFLOW – User SQLAlchemy model (re-exported for clean imports).
The canonical model is in app/models/models.py.
This module keeps the User class importable from app.models.user
for backward compatibility with generated code paths.
"""
from app.models.models import User  # noqa: F401
