"""Persistent background-job queue for ProjectReady AI."""

from app.jobs.store import init_job_tables

__all__ = ["init_job_tables"]
