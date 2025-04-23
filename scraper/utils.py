import json
from typing import Any, AsyncGenerator, TypeVar, Callable

import httpx
from collections import defaultdict
import random
import string
import os
import sys
import traceback
from .logger import logger

T = TypeVar("T")

async def gather(gen: AsyncGenerator[T, None]) -> list[T]:
    """Collects all items from an async generator into a list."""
    items = []
    async for x in gen:
        items.append(x)
    return items


def encode_params(obj: dict):
    """Encodes dictionary parameters for HTTP requests, JSON-encoding nested dicts."""
    res = {}
    for k, v in obj.items():
        if isinstance(v, dict):
            # Filter out None values before JSON encoding
            v = {a: b for a, b in v.items() if b is not None}
            v = json.dumps(v, separators=(",", ":"))
        res[k] = str(v)
    return res


def get_or(obj: dict, key: str, default_value: T = None) -> Any | T:
    """Safely gets a value from a nested dictionary using dot notation."""
    try:
        for part in key.split("."):
            if not isinstance(obj, dict) or part not in obj:
                return default_value
            obj = obj[part]
        return obj
    except Exception:
        return default_value

def int_or(obj: dict, key: str, default_value: int | None = None) -> int | None:
    """Safely gets an integer value from a nested dictionary."""
    try:
        val = get_or(obj, key)
        return int(val) if val is not None else default_value
    except (ValueError, TypeError):
        return default_value

# --- Parsing Helper Functions (needed by models.py) ---

# https://stackoverflow.com/a/43184871
def get_by_path(obj: dict, key: str, default=None):
    """Finds a value in a nested structure by key name, regardless of path."""
    stack = [iter(obj.items())]
    while stack:
        for k, v in stack[-1]:
            if k == key:
                return v
            elif isinstance(v, dict):
                stack.append(iter(v.items()))
                break
            elif isinstance(v, list):
                stack.append(iter(enumerate(v)))
                break
        else:
            stack.pop()
    return default

def find_item(lst: list[T], fn: Callable[[T], bool]) -> T | None:
    """Finds the first item in a list that matches the predicate."""
    for item in lst:
        if fn(item):
            return item
    return None

def get_typed_object(obj: dict, res: defaultdict[str, list]):
    """Recursively finds objects by __typename in a Twitter API response."""
    obj_type = obj.get("__typename", None)
    if obj_type is not None:
        res[obj_type].append(obj)

    for _, v in obj.items():
        if isinstance(v, dict):
            get_typed_object(v, res)
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, dict):
                    get_typed_object(x, res)
    return res

def to_old_obj(obj: dict):
    """Converts a new-style API object (with legacy nested) to the old flat structure."""
    # Ensure 'rest_id' exists before attempting conversion
    rest_id = obj.get("rest_id")
    if not rest_id:
        # Handle cases where rest_id might be missing or nested differently
        # This might indicate an unexpected structure or a different object type
        # logger.warning(f"Missing 'rest_id' in object: {json.dumps(obj)[:100]}...")
        return None # Or raise an error, depending on desired strictness

    legacy_data = obj.get("legacy", {})
    if not legacy_data:
        # logger.warning(f"Missing 'legacy' data for rest_id {rest_id}")
        # Decide how to handle: return partial data or None/error
        legacy_data = {} # Provide an empty dict to avoid errors below

    # Combine top-level, legacy, and derived fields
    combined = {
        **obj,
        **legacy_data,
        "id_str": str(rest_id),
        "id": int(rest_id),
        # "legacy": None, # Optionally remove the nested legacy field
    }
    # Explicitly remove the original 'legacy' key if desired, to avoid redundancy
    if 'legacy' in combined:
        del combined['legacy']
    return combined


def to_old_rep(obj: dict) -> dict[str, dict]:
    """Converts a raw GraphQL response into the snscrape-like flat dictionary format."""
    tmp = get_typed_object(obj, defaultdict(list))
    res = {"tweets": {}, "users": {}} # Initialize with empty dicts

    # Process Tweets (handling potential nesting and missing keys)
    raw_tweets = tmp.get("Tweet", []) + [
        item.get("tweet") for item in tmp.get("TweetWithVisibilityResults", []) if isinstance(item.get("tweet"), dict)
    ]

    for tw_data in raw_tweets:
        if isinstance(tw_data, dict) and "legacy" in tw_data and "rest_id" in tw_data:
             # Skip conversion if to_old_obj returns None (due to missing fields)
            old_tweet = to_old_obj(tw_data)
            if old_tweet and isinstance(old_tweet.get("id_str"), str):
                 res["tweets"][old_tweet["id_str"]] = old_tweet
        # else:
            # logger.debug(f"Skipping tweet conversion, missing legacy or rest_id: {json.dumps(tw_data)[:100]}...")


    # Process Users
    raw_users = tmp.get("User", [])
    for user_data in raw_users:
         if isinstance(user_data, dict) and "legacy" in user_data and "rest_id" in user_data:
            old_user = to_old_obj(user_data)
            if old_user and isinstance(old_user.get("id_str"), str):
                res["users"][old_user["id_str"]] = old_user
        # else:
        #     logger.debug(f"Skipping user conversion, missing legacy or rest_id: {json.dumps(user_data)[:100]}...")


    # Removed Trends processing as it's not needed for user timeline

    return res
def find_obj(obj: dict, fn: Callable[[dict], bool]) -> Any | None:
    if not isinstance(obj, dict):
        return None

    if fn(obj):
        return obj

    for _, v in obj.items():
        if isinstance(v, dict):
            if res := find_obj(v, fn):
                return res
        elif isinstance(v, list):
            for x in v:
                if res := find_obj(x, fn):
                    return res

    return None

# --- New function to fix the import error ---
def _write_dump(filename: str, data: Any) -> None:
    """Debug utility function to write data to a file for inspection."""
    try:
        dump_dir = "dumps"
        os.makedirs(dump_dir, exist_ok=True)
        
        filepath = os.path.join(dump_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            if isinstance(data, str):
                f.write(data)
            else:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        logger.debug(f"Dump written to {filepath}")
    except Exception as e:
        logger.error(f"Failed to write dump: {e}")

