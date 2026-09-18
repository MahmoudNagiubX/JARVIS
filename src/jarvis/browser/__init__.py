"""Deterministic browser controllers and optional Playwright boundary."""

from .policy import BrowserURLPolicy, BrowserURLPolicyError
from .profile import BrowserProfilePolicy, BrowserProfilePolicyError, standard_brave_executable_paths, validate_brave_executable_path
from .service import BrowserActionService, LocalBrowserController, PlaywrightBrowserController

__all__ = [
    "BrowserActionService",
    "BrowserProfilePolicy",
    "BrowserProfilePolicyError",
    "BrowserURLPolicy",
    "BrowserURLPolicyError",
    "LocalBrowserController",
    "PlaywrightBrowserController",
    "standard_brave_executable_paths",
    "validate_brave_executable_path",
]
