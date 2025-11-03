"""
Tank API - Generic Flask API layer for Tank applications
"""

from .app import create_app, run, app

__version__ = "1.0.0"
__all__ = ['create_app', 'run', 'app']

