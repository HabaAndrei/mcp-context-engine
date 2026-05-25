"""
Environment Variables Configuration Module

This module provides a thread-safe singleton class for loading and accessing
environment variables from a .env file. It automatically searches for the
.env file starting from the module's directory and traversing up to parent
directories until found.
"""

from threading import Lock
from pathlib import Path
from dotenv import load_dotenv
import os


class EnvVars:
    """
    Thread-safe singleton class for environment variable management.

    Uses the singleton pattern to ensure only one instance exists across
    the application, preventing multiple .env file loads and providing
    a consistent view of environment variables.
    """

    _instance = None  # Holds the single instance of the class
    _lock = Lock()    # Thread lock to ensure thread-safe instantiation

    def __new__(cls):
        """
        Creates a new instance only if one doesn't exist.
        Uses a lock to prevent race conditions in multi-threaded environments.
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        """
        Initializes the instance by loading environment variables.
        Only runs once due to the _initialized flag check.
        """
        if self._initialized:
            return
        self._initialized = True

        # Find and load the .env file if it exists
        env_file = self._find_env_file()
        if env_file:
            load_dotenv(env_file, override=True)

        # Store a copy of all environment variables (not a reference)
        # This ensures the values are captured at initialization time
        self._envs = dict(os.environ)

    def _find_env_file(self):
        """
        Searches for a .env file starting from this module's directory
        and traversing up through parent directories until found.

        Returns:
            Path to the .env file if found, None otherwise.
        """
        current = Path(__file__).resolve().parent
        while current != current.parent:  # Stop at filesystem root
            env_path = current / ".env"
            if env_path.exists():
                return env_path
            current = current.parent
        return None

    def get(self, name: str, default_var=None):
        """
        Retrieves an environment variable by name.

        Args:
            name: The name of the environment variable to retrieve.
            default_var: Value to return if the variable is not found.

        Returns:
            The value of the environment variable, or default_var if not found.
        """
        return self._envs.get(name, default_var)


# Pre-instantiated singleton instance for convenient import
# Usage: from config_env import env_vars
env_vars = EnvVars()