"""
Function to fetch user ID by screen name/username using Twitter/X GraphQL API.
"""
import json
import httpx
from typing import Dict, Optional

from .logger import logger
from .account import Account
from .models import User, parse_user
from .utils import encode_params, get_by_path, find_obj

# GraphQL operation for fetching user by screen name
OP_UserByScreenName = "32pL5BWe9WKeSK1MoPvFQQ/UserByScreenName"
GQL_URL = "https://x.com/i/api/graphql"  # Base URL for GraphQL API

# Default feature flags for user lookup
USER_FEATURES = {
    # Core features required by the API to prevent 400 errors
    "rweb_tipjar_consumption_enabled": True,  # Added this required feature
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "tweetypie_unmention_optimization_enabled": True,
    
    # User profile specific features
    "highlights_tweets_tab_ui_enabled": True,
    "hidden_profile_likes_enabled": True,
    "hidden_profile_subscriptions_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "subscriptions_verification_info_is_identity_verified_enabled": False,
    "responsive_web_twitter_article_notes_tab_enabled": False,
    "subscriptions_feature_can_gift_premium": False,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    
    # Additional features to match those used in fetch_tweets.py
    "longform_notetweets_consumption_enabled": True, 
    "longform_notetweets_rich_text_read_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "articles_preview_enabled": True,
    "rweb_video_timestamps_enabled": True,
}


async def fetch_user_by_login(account: Account, login_username: str) -> User | None:
    """
    Fetches and parses user profile information by their login username.

    Args:
        account: An Account instance with valid auth tokens.
        login_username: The target user's screen name (e.g., "xdevelopers").

    Returns:
        A User object if found and parsed successfully, otherwise None.
    """
    op = OP_UserByScreenName
    variables = {
        "screen_name": login_username,
        "withSafetyModeUserFields": True  # Commonly used field
    }

    logger.info(f"Attempting to fetch user ID for username: @{login_username}")
    
    # Use a context manager for the HTTP client
    async with account.make_client() as client:
        logger.debug(f"Using account '{account.username}' for user lookup")
        
        # Prepare request parameters
        params = {"variables": variables, "features": USER_FEATURES}
        request_url = f"{GQL_URL}/{op}"
        encoded_params = encode_params(params)  # Encode params including JSON serialization
        
        try:
            logger.trace(f"Making request to {request_url} with params: {json.dumps(params['variables'])}")
            response = await client.get(request_url, params=encoded_params)
            response.raise_for_status()  # Raise exception for 4xx/5xx errors
            
            # Check for GraphQL errors in the response
            obj = response.json()
            if "errors" in obj:
                logger.warning(f"GraphQL errors in response: {obj['errors']}")
                if any("Could not find user" in e.get("message", "") for e in obj["errors"]):
                    logger.warning(f"User not found: @{login_username}")
                    return None
            
            # Parse the user from the response
            user = parse_user(response)
            if user:
                logger.info(f"Successfully found user @{user.username} with ID: {user.id_str}")
                return user
            else:
                logger.warning(f"Could not parse user information for @{login_username} from the response.")
                return None
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching user: {e.response.status_code} - {e.request.url}")
            logger.error(f"Response body: {e.response.text[:500]}")
            return None
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON response for user lookup")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in fetch_user_by_login: {type(e)} - {e}")
            raise 