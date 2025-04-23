"""
Functions to fetch tweets from a user's timeline using Twitter/X GraphQL API.
"""

from contextlib import aclosing
import json
import httpx
from typing import AsyncGenerator, Dict, List, Optional, TypeVar, Union

from .logger import logger
from .account import Account
from .models import Tweet, User, parse_tweets
from .utils import encode_params, get_by_path, find_obj

# GraphQL constants
OP_UserTweets = "iXH7ZKZLgatGaM6ZAWc-cw/UserTweets"  # Operation ID for user tweets
GQL_URL = "https://x.com/i/api/graphql"  # Base URL for GraphQL API

# Default feature flags for tweet requests
TWEET_FEATURES = {
    "rweb_video_screen_enabled": False,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": False,
    "responsive_web_jetfuel_frame": False,
    "responsive_web_grok_share_attachment_enabled": False,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_grok_analysis_button_from_backend": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_grok_image_annotation_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
    "tweetypie_unmention_optimization_enabled": True,
    "rweb_video_timestamps_enabled": True,
}

# Default field toggles for tweet requests
TWEET_FIELD_TOGGLES = {
    "withArticlePlainText": False
}

# Type alias for key-value dictionaries (GraphQL variables)
KV = dict | None


def _get_cursor(obj: dict, cursor_type="Bottom") -> str | None:
    """Extracts the pagination cursor from a GraphQL response."""
    # Uses find_obj utility for robust searching
    cur = find_obj(obj, lambda x: isinstance(x, dict) and x.get("cursorType") == cursor_type)
    return cur.get("value") if cur else None


async def fetch_user_tweets(account: Account, user_id: int, limit: int = -1, 
                           kv: KV = None, field_toggles: dict = None) -> List[Tweet]:
    """
    Fetches and parses tweets from a user's timeline using a straightforward approach.
    
    Args:
        account: An Account instance with valid auth tokens.
        user_id: The numerical ID of the target user.
        limit: Maximum number of tweets to fetch (-1 for no limit).
        kv: Additional GraphQL variables to override defaults.
        field_toggles: Optional field toggles to override defaults.
    
    Returns:
        A list of Tweet objects, up to the specified limit.
    
    Raises:
        ValueError: If the account cannot be loaded or the API response is invalid.
        httpx.HTTPStatusError: If an HTTP error occurs during the request.
    """
    all_tweets = []
    logger.info(f"Fetching tweets for user ID: {user_id} (limit: {limit})")
    
    # Setup API parameters
    op = OP_UserTweets
    variables = {
        "userId": str(user_id),
        "count": 10,  # Reduced count per page to avoid timeouts
        "includePromotedContent": True,
        "withQuickPromoteEligibilityTweetFields": True,
        "withVoice": True,
        **(kv or {}),  # Allow overrides
    }
    features = TWEET_FEATURES
    ft = field_toggles or TWEET_FIELD_TOGGLES
    
    cursor = None  # Start with no cursor for the first request
    has_more = True  # Flag to indicate if more tweets are available
    total_fetched = 0  # Track total number of tweets fetched
    
    async with account.make_client() as client:
        logger.debug(f"Using account '{account.username}' for fetching tweets of user ID: {user_id}")
        
        # Continue fetching in a loop until we hit the limit or run out of tweets
        while has_more:
            # Prepare parameters for this request
            params = {"variables": {**variables}, "features": features}
            if cursor is not None:
                params["variables"]["cursor"] = cursor
            
            # Add field toggles
            params["fieldToggles"] = ft
            
            request_url = f"{GQL_URL}/{op}"
            encoded_params = encode_params(params)
            
            try:
                logger.trace(f"Making tweet request to {request_url} with params: {json.dumps(params['variables'])}")
                rep = await client.get(request_url, params=encoded_params)
                rep.raise_for_status()
                
                # --- Process Response ---
                obj = rep.json()
                
                # Basic error check
                if "errors" in obj:
                    logger.warning(f"GraphQL errors in response: {obj['errors']}")
                
                # Extract entries from response
                entries_container = get_by_path(obj, 'data.user.result.timeline_v2.timeline.instructions')
                
                entries = []
                if isinstance(entries_container, list):
                    for instruction in entries_container:
                        # Look for 'TimelineAddEntries' or similar instruction type
                        if instruction.get('type') in ('TimelineAddEntries', 'TimelineAddToModule') and isinstance(instruction.get('entries'), list):
                            entries.extend(instruction['entries'])
                        # Handle potential pinned tweet structure
                        elif instruction.get('type') == 'TimelinePinEntry' and isinstance(instruction.get('entry'), dict):
                            entries.append(instruction['entry'])
                
                # Filter out cursors and other non-tweet entries
                content_entries = [
                    e.get("content") for e in entries
                    if isinstance(e, dict) and isinstance(e.get("content"), dict) and \
                    (
                        # Entry types containing actual tweets
                        e.get("content", {}).get("entryType") == "TimelineTimelineItem" or \
                        # Entry types for cursors
                        e.get("content", {}).get("entryType") == "TimelineTimelineCursor"
                    )
                ]
                
                # Separate tweets
                tweet_items = [e for e in content_entries if e.get("itemContent", {}).get("itemType") == "TimelineTweet"]
                current_page_count = len(tweet_items)
                total_fetched += current_page_count
                logger.trace(f"Found {current_page_count} tweets on this page. Total fetched: {total_fetched}")
                
                # Parse tweets from this page
                parsed_count_on_page = 0
                for tweet in parse_tweets(rep, limit=limit):
                    if limit == -1 or len(all_tweets) < limit:
                        all_tweets.append(tweet)
                        parsed_count_on_page += 1
                    else:
                        # We've reached our limit, stop fetching more
                        has_more = False
                        break
                
                logger.debug(f"Parsed {parsed_count_on_page} tweets from page. Total collected: {len(all_tweets)}")
                
                # Find the 'Bottom' cursor for the next page
                cursor = _get_cursor(obj, cursor_type="Bottom")
                
                # Determine if we should continue fetching
                if not cursor:
                    has_more = False
                    logger.debug("No more tweets available (no cursor found).")
                elif limit != -1 and len(all_tweets) >= limit:
                    has_more = False
                    logger.info(f"Reached requested limit of {limit} tweets.")
                elif current_page_count == 0:
                    has_more = False
                    logger.debug("No tweets on current page, stopping pagination.")
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching tweets: {e.response.status_code} - {e.request.url}")
                logger.error(f"Response body: {e.response.text[:500]}")
                raise
            except (json.JSONDecodeError, Exception) as e:
                logger.error(f"Error processing tweet response: {type(e)} - {e}")
                raise
    
    # Ensure we don't return more than the requested limit
    return all_tweets[:limit] if limit != -1 else all_tweets 