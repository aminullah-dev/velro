"""Interfaces the application layer declares and the infrastructure implements.

Nothing here imports SQLAlchemy, FastAPI or an HTTP client. That is what lets a
use case be tested with in-memory fakes in milliseconds, and what makes the
choice of database a configuration detail rather than an architectural one.
"""
