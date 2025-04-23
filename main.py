import asyncio
import os
import httpx # Import httpx for error handling
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv  # Import dotenv for loading .env files

# Load environment variables from .env file
load_dotenv()

# Import necessary components from our package
from scraper import (
    Account,
    User,
    set_log_level,
    # Import the new functions
    fetch_user_by_login,
    fetch_user_tweets
)
from scraper.logger import logger

async def main():
    # Configure logging level (optional, INFO is default)
    set_log_level("DEBUG")
    #set_log_level("INFO")

    # --- Configuration ---
    # Read target usernames from file
    accounts_file = "target_accounts.txt"
    if not Path(accounts_file).exists():
        logger.error(f"Accounts file '{accounts_file}' not found. Please create it with one username per line.")
        return
    with open(accounts_file, "r", encoding="utf-8") as f:
        target_usernames = [
            line.strip() for line in f
            if line.strip() and not line.strip().startswith('#')
        ]
    if not target_usernames:
        logger.error(f"No usernames found in '{accounts_file}'. Please add at least one username.")
        return
    tweet_limit = 10 # Max number of tweets to fetch per user (-1 for no limit)

    # --- Delay Configuration ---
    try:
        delay_between_accounts = float(os.environ.get("DELAY_BETWEEN_ACCOUNTS", 1))
        if delay_between_accounts < 0:
            raise ValueError
    except (ValueError, TypeError):
        delay_between_accounts = 1.0
    logger.info(f"Delay between processing each account: {delay_between_accounts} seconds")

    # --- Account Setup ---
    # Get credentials from environment variables or use defaults
    auth_token = os.environ.get("TW_AUTH_TOKEN") or ""
    ct0_token = os.environ.get("TW_CT0_TOKEN") or ""

    if not auth_token or not ct0_token:
         logger.error("Please set your auth_token and ct0 token in main.py or via environment variables (TW_AUTH_TOKEN, TW_CT0_TOKEN).")
         logger.error("See README.md for instructions on how to find these values.")
         return # Exit if tokens are not set

    # Create account directly without saving to file
    account = Account(
        username="my_account",  # This can be any identifier you want to use
        auth_token=auth_token,
        ct0=ct0_token
        # user_agent is optional and will be auto-generated if not provided
    )
    logger.info(f"Using account: '{account.username}'")

    # --- Create output folder if it doesn't exist ---
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    logger.info(f"Saving results to {output_dir} folder")

    # Process each target username
    for target_username in target_usernames:
        logger.info(f"Processing user: @{target_username}")
        
        # --- Fetch User ID ---
        logger.info(f"Looking up user ID for @{target_username}...")
        target_user: User | None = None
        try:
            # Use the new function to look up the user by username
            target_user = await fetch_user_by_login(account, target_username)

            if not target_user:
                logger.error(f"Could not find user @{target_username}. Skipping and continuing to next user.")
                continue # Skip to next user if not found

            target_user_id = target_user.id # Extract the ID from the User object

        except ValueError as e:
            logger.error(f"Configuration error during user lookup for @{target_username}: {e}")
            continue # Skip to next user
        except Exception as e:
            logger.exception(f"An unexpected error occurred during user lookup for @{target_username}: {e}")
            continue # Skip to next user

        # --- Fetch Tweets (using the obtained ID) ---
        logger.info(f"Fetching timeline for user @{target_username} (ID: {target_user_id}, limit: {tweet_limit})")
        try:
            # Use the new function to fetch and parse tweets directly into a list
            tweets = await fetch_user_tweets(account, user_id=target_user_id, limit=tweet_limit)

            logger.info(f"Successfully fetched {len(tweets)} tweets for @{target_username}.")
            # --- Process Results ---
            if tweets:
                logger.info(f"--- Example Tweets for @{target_username} ---")
                for i, tweet in enumerate(tweets[:3]): # Print first 3 tweets as examples
                    print(f"Tweet {i+1}/{len(tweets)}:")
                    print(f"  ID: {tweet.id_str}")
                    print(f"  User: @{tweet.user.username} ({tweet.user.displayname})")
                    print(f"  Date: {tweet.date}")
                    # Replace newlines in content for cleaner printing
                    content_cleaned = tweet.rawContent.replace('\n', ' ') if tweet.rawContent else ""
                    print(f"  Content: {content_cleaned[:100]}...") # Print snippet
                    print(f"  URL: {tweet.url}")
                    print("-" * 20)
                
                # --- Save the results to a JSON file in the output folder ---
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # Save the tweets to the output folder with username in filename
                tweets_output_file = output_dir / f"tweets_{target_username}_{timestamp}.json"
                
                with open(tweets_output_file, "w", encoding="utf-8") as f:
                    # Convert each Tweet object to its dictionary representation
                    json.dump([tweet.dict() for tweet in tweets], f, indent=2, ensure_ascii=False, default=str)
                logger.info(f"Tweets saved to {tweets_output_file}")
                
                # Save user metadata to a separate file in the output folder
                metadata_output_file = output_dir / f"user_metadata_{target_username}_{timestamp}.json"
                
                # Create metadata dictionary with user info and scrape info
                metadata = {
                    "scrape_info": {
                        "timestamp": datetime.now().isoformat(),
                        "tweets_collected": len(tweets),
                        "tweet_limit_setting": tweet_limit,
                        "scraper_version": "1.0.0"
                    },
                    "user_info": target_user.dict() if target_user else {}
                }
                
                with open(metadata_output_file, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)
                logger.info(f"User metadata saved to {metadata_output_file}")
                
            else:
                logger.info(f"No tweets found for @{target_username} or an error occurred during fetching.")

        except ValueError as e:
            logger.error(f"Configuration error during tweet fetching for @{target_username}: {e}")
        except httpx.HTTPStatusError as e:
             logger.error(f"HTTP error occurred during tweet fetching for @{target_username}: {e.response.status_code} - Check account credentials/validity.")
             # Log response body if available
             try:
                logger.error(f"Response Body: {e.response.text}")
             except Exception:
                 logger.error("Could not read error response body.")
        except Exception as e:
            logger.exception(f"An unexpected error occurred during tweet fetching for @{target_username}: {e}") # Logs traceback
        
        logger.info(f"Completed processing for @{target_username}")
        logger.info("-" * 40)
        # --- Adjustable delay between accounts ---
        if target_username != target_usernames[-1]:
            logger.debug(f"Sleeping for {delay_between_accounts} seconds before next account...")
            await asyncio.sleep(delay_between_accounts)

    logger.info("Completed processing all target usernames")

if __name__ == "__main__":
    asyncio.run(main())