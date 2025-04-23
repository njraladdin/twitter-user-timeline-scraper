# ruff: noqa: F401
# Expose key classes and functions for easier import
from .account import Account
from .models import Tweet, User, parse_tweets, parse_user
from .utils import gather
from .logger import set_log_level

# Import the new straightforward functions
from .fetch_user_id import fetch_user_by_login
from .fetch_tweets import fetch_user_tweets

__version__ = "0.1.0" # Simple versioning