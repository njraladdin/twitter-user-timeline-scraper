import email.utils
import json
import re
import traceback  # Import traceback for better error reporting
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Generator, Optional, Union

import httpx

from .logger import logger
from .utils import find_item, get_or, int_or, to_old_rep, _write_dump, get_by_path # Assuming these utils are kept

# --- Base Class ---
@dataclass
class JSONTrait:
    """Mixin for easy dictionary and JSON conversion."""
    def dict(self):
        return asdict(self)

    def json(self):
        return json.dumps(self.dict(), default=str)

# --- Basic Types ---
@dataclass
class TextLink(JSONTrait):
    url: str
    text: str | None
    tcourl: str | None # The t.co shortened URL

    @staticmethod
    def parse(obj: dict):
        # Handle potential missing keys gracefully
        expanded_url = obj.get("expanded_url")
        tco_url = obj.get("url")

        # Ensure essential URLs are present
        if not expanded_url or not tco_url:
            # logger.debug(f"Skipping TextLink due to missing URL: {obj}")
            return None

        return TextLink(
            url=expanded_url,
            text=obj.get("display_url"), # Optional
            tcourl=tco_url,
        )

@dataclass
class UserRef(JSONTrait):
    """Represents a user mention or reference."""
    id: int
    id_str: str
    username: str # screen_name
    displayname: str # name
    _type: str = "twitter_user_timeline_scraper.UserRef" # Updated type string

    @staticmethod
    def parse(obj: dict):
         # Basic validation for required fields
        id_str = obj.get("id_str")
        screen_name = obj.get("screen_name")
        name = obj.get("name")

        if not all([id_str, screen_name, name]):
            # logger.warning(f"Skipping UserRef due to missing fields: {obj}")
            return None
        try:
            user_id = int(id_str)
        except (ValueError, TypeError):
            # logger.warning(f"Skipping UserRef due to invalid id_str: {id_str}")
            return None

        return UserRef(
            id=user_id,
            id_str=id_str,
            username=screen_name,
            displayname=name,
        )


# --- Core Models ---

@dataclass
class User(JSONTrait):
    """Represents a Twitter/X User profile."""
    id: int
    id_str: str
    url: str
    username: str
    displayname: str
    rawDescription: str # The raw description text
    created: datetime
    # Counts - provide defaults
    followersCount: int = 0
    friendsCount: int = 0 # Following count
    statusesCount: int = 0 # Tweets count
    favouritesCount: int = 0 # Likes count
    listedCount: int = 0
    mediaCount: int = 0
    # Profile details - provide defaults
    location: str = ""
    profileImageUrl: str = ""
    profileBannerUrl: str | None = None
    # Status flags - provide defaults
    protected: bool | None = None
    verified: bool | None = None # Legacy verification checkmark
    blue: bool | None = None # Twitter Blue checkmark
    blueType: str | None = None # e.g., "business"
    # Processed fields
    descriptionLinks: list[TextLink] = field(default_factory=list) # Links parsed from description
    pinnedIds: list[int] = field(default_factory=list) # IDs of pinned tweets (as ints)
    _type: str = "twitter_user_timeline_scraper.User" # Updated type string


    @staticmethod
    def parse(obj: dict, res=None): # res is the larger context, unused here but kept for potential compatibility
        # Essential fields check
        id_str = obj.get("id_str")
        screen_name = obj.get("screen_name")
        name = obj.get("name")
        created_at_str = obj.get("created_at")

        if not all([id_str, screen_name, name, created_at_str]):
             logger.warning(f"Skipping User parse due to missing essential fields: {obj.get('id_str')}")
             return None

        try:
            user_id = int(id_str)
            created_dt = email.utils.parsedate_to_datetime(created_at_str)
        except (ValueError, TypeError):
             logger.warning(f"Skipping User parse due to invalid ID or date: {obj.get('id_str')}")
             return None


        # Parse description links safely
        desc_links = _parse_links(obj, ["entities.description.urls", "entities.url.urls"])

        # Parse pinned tweet IDs safely
        pinned_ids_str = obj.get("pinned_tweet_ids_str", [])
        pinned_ids_int = []
        for pid_str in pinned_ids_str:
            try:
                pinned_ids_int.append(int(pid_str))
            except (ValueError, TypeError):
                logger.debug(f"Skipping invalid pinned tweet ID: {pid_str} for user {id_str}")


        return User(
            id=user_id,
            id_str=id_str,
            url=f"https://x.com/{screen_name}",
            username=screen_name,
            displayname=name,
            rawDescription=obj.get("description", ""),
            created=created_dt,
            followersCount=obj.get("followers_count", 0),
            friendsCount=obj.get("friends_count", 0),
            statusesCount=obj.get("statuses_count", 0),
            favouritesCount=obj.get("favourites_count", 0),
            listedCount=obj.get("listed_count", 0),
            mediaCount=obj.get("media_count", 0),
            location=obj.get("location", ""),
            profileImageUrl=obj.get("profile_image_url_https", ""),
            profileBannerUrl=obj.get("profile_banner_url"), # Optional
            protected=obj.get("protected"), # Optional bool
            verified=obj.get("verified"), # Optional bool
            blue=obj.get("is_blue_verified"), # Optional bool
            blueType=obj.get("verified_type"), # Optional str
            descriptionLinks=desc_links,
            pinnedIds=pinned_ids_int,
        )

@dataclass
class Tweet(JSONTrait):
    """Represents a single Tweet."""
    id: int
    id_str: str
    url: str
    date: datetime
    user: User # The author of the tweet
    lang: str
    rawContent: str # The main text content of the tweet
    conversationId: int  # Moved up before fields with defaults
    conversationIdStr: str  # Moved up before fields with defaults
    # Engagement counts - provide defaults
    replyCount: int = 0
    retweetCount: int = 0
    likeCount: int = 0 # favorite_count
    quoteCount: int = 0
    # Note: bookmarkedCount is often not available for timelines, requires specific endpoint
    bookmarkedCount: int | None = None # Changed to optional
    # Parsed entities - provide defaults
    hashtags: list[str] = field(default_factory=list)
    cashtags: list[str] = field(default_factory=list)
    mentionedUsers: list[UserRef] = field(default_factory=list)
    links: list[TextLink] = field(default_factory=list)
    media: Optional["Media"] = None # Media object (photos, videos, gifs)
    # Optional fields
    viewCount: int | None = None
    retweetedTweet: Optional["Tweet"] = None # If this tweet is a retweet
    quotedTweet: Optional["Tweet"] = None # If this tweet quotes another tweet
    inReplyToTweetId: int | None = None
    inReplyToTweetIdStr: str | None = None
    inReplyToUser: Optional[UserRef] = None # User reference if it's a reply
    # Source (e.g., "Twitter Web App")
    source: str | None = None
    sourceUrl: str | None = None
    sourceLabel: str | None = None
    possibly_sensitive: bool | None = None # Content warning flag
    _type: str = "twitter_user_timeline_scraper.Tweet" # Updated type string

    # Removed Place, Coordinates, Card as they are less common in basic timelines
    # or require more complex parsing logic not requested

    @staticmethod
    def parse(obj: dict, res: dict): # res contains the full response context (users, tweets)
        # --- Essential Field Validation ---
        id_str = obj.get("id_str")
        user_id_str = obj.get("user_id_str")
        created_at_str = obj.get("created_at")
        conversation_id_str = obj.get("conversation_id_str")

        if not all([id_str, user_id_str, created_at_str, conversation_id_str]):
            logger.warning(f"Skipping Tweet parse: Missing essential fields in object {id_str or 'UNKNOWN'}")
            return None

        # --- User Parsing ---
        user_data = res.get("users", {}).get(user_id_str)
        if not user_data:
            logger.warning(f"Skipping Tweet parse {id_str}: User {user_id_str} not found in response context.")
            return None
        tw_usr = User.parse(user_data) # Use the User model's parser
        if not tw_usr:
            logger.warning(f"Skipping Tweet parse {id_str}: Failed to parse User {user_id_str}.")
            return None

        # --- Basic Type Conversions and Fallbacks ---
        try:
            tweet_id = int(id_str)
            conversation_id = int(conversation_id_str)
            created_dt = email.utils.parsedate_to_datetime(created_at_str)
        except (ValueError, TypeError) as e:
            logger.warning(f"Skipping Tweet parse {id_str}: Invalid ID, conversation ID, or date format. Error: {e}")
            return None

        # --- Content Determination (handle potential 'note_tweet') ---
        raw_content = get_or(obj, "note_tweet.note_tweet_results.result.text", obj.get("full_text", ""))

        # --- Recursive Parsing for Retweeted/Quoted Tweets ---
        rt_obj = get_or(res, f"tweets.{obj.get('retweeted_status_id_str')}")
        qt_obj = get_or(res, f"tweets.{obj.get('quoted_status_id_str')}")

        retweeted_tweet = None
        if rt_obj:
            # Avoid infinite recursion if a tweet retweets itself (unlikely but possible)
            if rt_obj.get("id_str") != id_str:
                retweeted_tweet = Tweet.parse(rt_obj, res)
            else:
                logger.warning(f"Detected self-retweet loop for tweet {id_str}. Skipping nested parse.")


        quoted_tweet = None
        if qt_obj:
             if qt_obj.get("id_str") != id_str: # Avoid self-quote loop
                quoted_tweet = Tweet.parse(qt_obj, res)
             else:
                logger.warning(f"Detected self-quote loop for tweet {id_str}. Skipping nested parse.")


        # --- Engagement Counts and Optional Fields ---
        view_count = _get_views(obj, rt_obj or {}) # Helper to get views, potentially from RT
        in_reply_to_user_ref = _get_reply_user(obj, res) # Helper to parse reply user

        # --- Entity Parsing ---
        hashtags = [tag.get("text") for tag in get_or(obj, "entities.hashtags", []) if tag.get("text")]
        cashtags = [tag.get("text") for tag in get_or(obj, "entities.symbols", []) if tag.get("text")]
        # Ensure mentioned user objects are valid before adding
        mentioned_users = [UserRef.parse(u) for u in get_or(obj, "entities.user_mentions", [])]
        mentioned_users = [u for u in mentioned_users if u is not None] # Filter out None results

        links = _parse_links(
            obj, ["entities.urls", "note_tweet.note_tweet_results.result.entity_set.urls"]
        )

        # --- Media Parsing ---
        media = Media.parse(obj) # Use the Media model's parser

        # --- Source Parsing ---
        source_html = obj.get("source")
        source_url = _get_source_url(source_html) if source_html else None
        source_label = _get_source_label(source_html) if source_html else None

        # --- Construct the Tweet Object ---
        doc = Tweet(
            id=tweet_id,
            id_str=id_str,
            url=f"https://x.com/{tw_usr.username}/status/{id_str}",
            date=created_dt,
            user=tw_usr,
            lang=obj.get("lang", "und"), # Default to 'undetermined'
            rawContent=raw_content,
            conversationId=conversation_id,
            conversationIdStr=conversation_id_str,
            replyCount=obj.get("reply_count", 0),
            retweetCount=obj.get("retweet_count", 0),
            likeCount=obj.get("favorite_count", 0),
            quoteCount=obj.get("quote_count", 0),
            bookmarkedCount=int_or(obj, "bookmark_count"), # Often None
            hashtags=hashtags,
            cashtags=cashtags,
            mentionedUsers=mentioned_users,
            links=links,
            media=media if (media and (media.photos or media.videos or media.animated)) else None, # Assign only if media exists
            viewCount=view_count,
            retweetedTweet=retweeted_tweet,
            quotedTweet=quoted_tweet,
            inReplyToTweetId=int_or(obj, "in_reply_to_status_id_str"),
            inReplyToTweetIdStr=obj.get("in_reply_to_status_id_str"),
            inReplyToUser=in_reply_to_user_ref,
            source=source_html, # Store raw source HTML
            sourceUrl=source_url,
            sourceLabel=source_label,
            possibly_sensitive=obj.get("possibly_sensitive"), # Optional bool
        )

        # --- Post-Processing (e.g., fix truncated retweet text) ---
        if doc.retweetedTweet and doc.rawContent.endswith("…"):
             rt = doc.retweetedTweet
             # Check if user exists to prevent errors
             if rt.user and rt.user.username:
                # Construct expected RT format and update if necessary
                expected_rt_text = f"RT @{rt.user.username}: {rt.rawContent}"
                # Heuristic: update only if the content seems genuinely truncated
                # Avoid replacing if rawContent already contains the start of expected_rt_text
                if not doc.rawContent.startswith(f"RT @{rt.user.username}:"):
                     doc.rawContent = expected_rt_text
                     logger.debug(f"Expanded truncated retweet text for {doc.id_str}")

        return doc


# --- Media Models ---

@dataclass
class MediaPhoto(JSONTrait):
    url: str

    @staticmethod
    def parse(obj: dict):
        url = obj.get("media_url_https")
        return MediaPhoto(url=url) if url else None

@dataclass
class MediaVideoVariant(JSONTrait):
    contentType: str
    bitrate: int
    url: str

    @staticmethod
    def parse(obj: dict):
        content_type = obj.get("content_type")
        bitrate = obj.get("bitrate") # Required by original logic
        url = obj.get("url")

        if not all([content_type, url]) or bitrate is None: # Bitrate is key
            # logger.debug(f"Skipping MediaVideoVariant due to missing fields: {obj}")
            return None
        try:
            # Ensure bitrate is int, handle potential string values if API changes
             bitrate_int = int(bitrate)
        except (ValueError, TypeError):
             # logger.warning(f"Skipping MediaVideoVariant due to invalid bitrate: {bitrate}")
             return None


        return MediaVideoVariant(
            contentType=content_type,
            bitrate=bitrate_int,
            url=url,
        )

@dataclass
class MediaVideo(JSONTrait):
    thumbnailUrl: str
    variants: list[MediaVideoVariant] # List of available video formats/qualities
    duration: int # Duration in milliseconds
    views: int | None = None # Optional view count

    @staticmethod
    def parse(obj: dict):
        thumb_url = obj.get("media_url_https")
        video_info = obj.get("video_info", {})
        duration_ms = video_info.get("duration_millis")
        variants_raw = video_info.get("variants", [])

        if not thumb_url or duration_ms is None or not variants_raw:
            # logger.debug(f"Skipping MediaVideo due to missing essential info: {obj.get('id_str')}")
            return None

        variants_parsed = [MediaVideoVariant.parse(v) for v in variants_raw]
        # Filter out variants that failed parsing AND variants without bitrate (as per original logic)
        variants_valid = [v for v in variants_parsed if v is not None and hasattr(v, 'bitrate')]


        # If no valid variants remain after filtering, don't create the MediaVideo object
        if not variants_valid:
             # logger.debug(f"Skipping MediaVideo: No valid variants found for media in tweet {obj.get('id_str')}")
             return None

        try:
            # Ensure duration is int
            duration_int = int(duration_ms)
        except (ValueError, TypeError):
             logger.warning(f"Skipping MediaVideo due to invalid duration: {duration_ms}")
             return None

        # Optional view count parsing
        view_count = int_or(obj, "mediaStats.viewCount") # Uses the safe int_or helper


        return MediaVideo(
            thumbnailUrl=thumb_url,
            variants=variants_valid,
            duration=duration_int,
            views=view_count,
        )


@dataclass
class MediaAnimated(JSONTrait): # Represents an animated GIF (usually implemented as a video)
    thumbnailUrl: str
    videoUrl: str # URL of the GIF's video representation

    @staticmethod
    def parse(obj: dict):
         thumb_url = obj.get("media_url_https")
         video_info = obj.get("video_info", {})
         variants = video_info.get("variants", [])

         # Basic validation
         if not thumb_url or not variants:
             # logger.debug(f"Skipping MediaAnimated due to missing info: {obj.get('id_str')}")
             return None

         # Animated GIFs typically have one variant
         video_url = variants[0].get("url") if variants and isinstance(variants[0], dict) else None

         if not video_url:
             # logger.debug(f"Skipping MediaAnimated: Could not find video URL in variant for {obj.get('id_str')}")
             return None

         return MediaAnimated(
             thumbnailUrl=thumb_url,
             videoUrl=video_url,
         )


@dataclass
class Media(JSONTrait):
    """Container for different types of media attached to a tweet."""
    photos: list[MediaPhoto] = field(default_factory=list)
    videos: list[MediaVideo] = field(default_factory=list)
    animated: list[MediaAnimated] = field(default_factory=list) # For GIFs

    @staticmethod
    def parse(obj: dict):
        photos: list[MediaPhoto] = []
        videos: list[MediaVideo] = []
        animated: list[MediaAnimated] = []

        # Use get_or for safe access to potentially missing media list
        media_list = get_or(obj, "extended_entities.media", [])

        for item in media_list:
            media_type = item.get("type")
            parsed_media = None # Initialize parsed_media for clarity

            if media_type == "photo":
                parsed_media = MediaPhoto.parse(item)
                if parsed_media: photos.append(parsed_media)
            elif media_type == "video":
                parsed_media = MediaVideo.parse(item)
                if parsed_media: videos.append(parsed_media)
            elif media_type == "animated_gif":
                parsed_media = MediaAnimated.parse(item)
                if parsed_media: animated.append(parsed_media)
            else:
                logger.warning(f"Unknown media type encountered: {media_type} in tweet {obj.get('id_str')}")


            # Optional: Log if parsing failed for a known type
            # if media_type in ["photo", "video", "animated_gif"] and not parsed_media:
                # logger.debug(f"Failed to parse media item of type {media_type} for tweet {obj.get('id_str')}")


        # Only return a Media object if it contains any parsed media
        if photos or videos or animated:
            return Media(photos=photos, videos=videos, animated=animated)
        else:
            return None


# --- Internal Helper Functions --- (Moved relevant ones from original models.py)

def _get_reply_user(tw_obj: dict, res: dict) -> UserRef | None:
    """Parses the user reference for a reply tweet."""
    user_id_str = tw_obj.get("in_reply_to_user_id_str")
    if not user_id_str:
        return None

    # 1. Try getting the full user object from the response context
    user_data = res.get("users", {}).get(user_id_str)
    if user_data:
        parsed_user_ref = UserRef.parse(user_data)
        if parsed_user_ref: return parsed_user_ref # Return if parsing succeeds

    # 2. Fallback: Try finding the user in the tweet's mentions
    mentions = get_or(tw_obj, "entities.user_mentions", [])
    mention_data = find_item(mentions, lambda x: isinstance(x, dict) and x.get("id_str") == user_id_str)
    if mention_data:
        parsed_mention_ref = UserRef.parse(mention_data)
        if parsed_mention_ref: return parsed_mention_ref # Return if parsing succeeds

    # 3. If not found or parsing failed, return None
    logger.debug(f"Could not find or parse reply user {user_id_str} for tweet {tw_obj.get('id_str')}")
    return None


def _get_source_url(source_html: str) -> str | None:
    """Extracts the URL from the source HTML string."""
    if not source_html: return None
    match = re.search(r'href=[\'"]?([^\'" >]+)', source_html)
    return str(match.group(1)) if match else None

def _get_source_label(source_html: str) -> str | None:
    """Extracts the text label from the source HTML string."""
    if not source_html: return None
    match = re.search(r">([^<]*)<", source_html)
    return str(match.group(1)) if match else None

def _parse_links(obj: dict, paths: list[str]) -> list[TextLink]:
    """Parses TextLink objects from specified paths within a dictionary."""
    links_raw = []
    for path in paths:
        # Safely get list of URLs from the current path
        path_links = get_or(obj, path, [])
        # Ensure we only add dictionaries (API format)
        links_raw.extend([link for link in path_links if isinstance(link, dict)])

    parsed_links = [TextLink.parse(link) for link in links_raw]
    # Filter out any links that failed parsing (returned None)
    return [link for link in parsed_links if link is not None]


def _get_views(obj: dict, rt_obj: dict) -> int | None:
    """Safely extracts view count, checking both tweet and potential retweet."""
    # Prioritize view count from the primary object ('obj')
    # Check common paths for view counts
    view_paths = ["ext_views.count", "view_count", "views.count"] # Add known variations

    for source_obj in [obj, rt_obj]: # Check original, then retweet if present
        if not isinstance(source_obj, dict): continue # Skip if rt_obj is None or not a dict
        for path in view_paths:
            views = int_or(source_obj, path) # Use safe integer parsing
            if views is not None:
                return views # Return the first valid view count found

    return None # Return None if no view count is found


# --- Public Parsing Entry Points ---

def parse_tweets(rep: httpx.Response | dict, limit: int = -1) -> Generator[Tweet, None, None]:
    """Parses tweets from an HTTP response or pre-parsed dictionary."""
    count = 0
    try:
        # Handle both httpx.Response and dict input
        res_data = rep if isinstance(rep, dict) else rep.json()
        obj = to_old_rep(res_data) # Convert to the snscrape-like format

        # Safely iterate through tweets
        tweet_dict = obj.get("tweets", {})
        if not isinstance(tweet_dict, dict):
            logger.error("Parsed tweet data is not a dictionary.")
            return # Stop generation if structure is wrong

        for tweet_id, tweet_data in tweet_dict.items():
             # Basic check if tweet_data is a dictionary before parsing
            if not isinstance(tweet_data, dict):
                 logger.warning(f"Skipping invalid tweet data for ID {tweet_id}")
                 continue


            if limit != -1 and count >= limit:
                break # Respect the limit

            try:
                parsed_tweet = Tweet.parse(tweet_data, obj)
                if parsed_tweet: # Check if parsing was successful
                    yield parsed_tweet
                    count += 1
            except Exception as e:
                 # Use the _write_dump utility on parsing failure for a specific tweet
                 logger.error(f"Error parsing individual tweet {tweet_id}. Error: {type(e)}")
                 _write_dump("tweet_item", e, tweet_data, obj)
                 # Continue to the next tweet instead of stopping the generator
                 continue


    except (json.JSONDecodeError, AttributeError, TypeError, Exception) as e:
        # Catch broader errors during initial processing or conversion
        logger.error(f"Failed to process or parse tweet response: {type(e)} - {e}")
        # Optionally dump the raw response if available and possible
        raw_data_to_dump = {}
        if isinstance(rep, httpx.Response):
             try:
                 raw_data_to_dump = {"raw_text": rep.text}
             except Exception: pass # Ignore errors reading raw text
        elif isinstance(rep, dict):
            raw_data_to_dump = rep # Dump the input dict

        # Avoid dumping excessively large data if the raw response was huge
        # _write_dump("tweet_response", e, {}, raw_data_to_dump) # Adapt _write_dump if needed

# NEW: Public parser for a single User object
def parse_user(rep: httpx.Response | dict) -> User | None:
    """
    Parses a single User object from an API response typically containing one user.

    Args:
        rep: The httpx.Response object or a pre-parsed dictionary.

    Returns:
        A User object if parsing is successful, otherwise None.
    """
    try:
        res_data = rep if isinstance(rep, dict) else rep.json()
        obj = to_old_rep(res_data) # Convert to the flat structure

        user_dict = obj.get("users", {})
        if not isinstance(user_dict, dict):
             logger.error("Parsed user data is not a dictionary.")
             return None

        if not user_dict:
            # This can happen if the user wasn't found by the API query
            logger.debug("No user found in the 'users' dictionary of the parsed response.")
            return None

        # Assuming UserByScreenName returns only one user in the dict
        if len(user_dict) > 1:
            logger.warning(f"Expected one user in response, found {len(user_dict)}. Parsing the first one.")

        # Get the first user's data from the dictionary values
        user_data = next(iter(user_dict.values()), None)

        if not user_data or not isinstance(user_data, dict):
            logger.error("Could not extract valid user data from the response.")
            return None

        # Parse the extracted user data using the User model's parser
        parsed_user = User.parse(user_data)
        return parsed_user

    except (json.JSONDecodeError, AttributeError, TypeError, Exception) as e:
        logger.error(f"Failed to parse user response: {type(e)}")
        # Optionally log traceback for unexpected errors
        logger.debug(traceback.format_exc()) # Log traceback on debug level
         # Optionally dump the response that failed parsing
        raw_data_to_dump = {}
        if isinstance(rep, httpx.Response):
             try: raw_data_to_dump = {"raw_text": rep.text}
             except Exception: pass
        elif isinstance(rep, dict): raw_data_to_dump = rep
        # Consider adapting _write_dump or creating a similar function for user parsing errors
        # _write_dump("user_response", e, {}, raw_data_to_dump)
        return None