"""Lexful QA harness server.

Importing the package makes the process's file writes refuse planted symlinks (see `safefs`).
"""

from app import safefs

safefs.install()
