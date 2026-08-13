"""E.V.'s web interface package: static frontend (.frontend) + FastAPI app
factory and routes (.app). Split out of the original monolithic
ev/interfaces/web.py in Phase 6a of the interfaces refactor.
"""

from .app import create_app, run

__all__ = ["create_app", "run"]
