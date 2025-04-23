import json
import os
from dataclasses import asdict, dataclass, field
from fake_useragent import UserAgent
from httpx import AsyncClient, AsyncHTTPTransport
from pathlib import Path

from .models import JSONTrait
from .logger import logger

# Hardcoded Bearer token (public web app key)
TOKEN = "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

# Default account file path
DEFAULT_ACCOUNT_FILE = "account.json"

@dataclass
class Account(JSONTrait):
    """Represents account credentials and state for API interaction."""
    username: str
    auth_token: str # Required cookie
    ct0: str        # Required cookie and CSRF token source
    user_agent: str = field(default_factory=lambda: UserAgent().chrome) # Generate default UA

    @staticmethod
    def from_dict(data: dict):
        """Creates an Account object from a dictionary (e.g., loaded from JSON)."""
        # Provide default user agent if not present in the loaded data
        data['user_agent'] = data.get('user_agent') or UserAgent().chrome
        return Account(**data)

    def to_dict(self) -> dict:
        """Converts the Account object to a dictionary for saving."""
        return asdict(self)

    def make_client(self, target_username: str = None) -> AsyncClient:
        """Creates and configures an httpx.AsyncClient for API requests.
        
        Args:
            target_username: Optional username being targeted for the referer header
        """
        # Standard transport with retries
        transport = AsyncHTTPTransport(retries=2)
        client = AsyncClient(follow_redirects=True, transport=transport)

        # Set essential headers
        client.headers["user-agent"] = self.user_agent
        client.headers["authorization"] = TOKEN # Use the hardcoded public Bearer token
        client.headers["content-type"] = "application/json"
        client.headers["accept"] = "*/*"
        client.headers["accept-language"] = "en-US,en;q=0.9"
        client.headers["priority"] = "u=1, i" # New priority header
        
        # Set referer if a target username is provided
        if target_username:
            client.headers["referer"] = f"https://x.com/{target_username}"
        
        # X/Twitter specific headers
        client.headers["x-twitter-active-user"] = "yes"
        client.headers["x-twitter-client-language"] = "en"
        client.headers["x-twitter-auth-type"] = "OAuth2Session"
        
        # Modern security headers
        client.headers["sec-ch-ua"] = '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"'
        client.headers["sec-ch-ua-mobile"] = "?0"
        client.headers["sec-ch-ua-platform"] = '"Windows"'
        client.headers["sec-fetch-dest"] = "empty"
        client.headers["sec-fetch-mode"] = "cors"
        client.headers["sec-fetch-site"] = "same-origin"

        # Set cookies required for authentication
        # Critical authentication cookies
        client.cookies.set("auth_token", self.auth_token)
        client.cookies.set("ct0", self.ct0)
        

        
        # Note: __cf_bm is a CloudFlare cookie that changes frequently and is set by the server
        # It's typically not needed to include this manually as it will be set by CloudFlare
        # during the first request and handled automatically by httpx's cookie jar

        # Set CSRF token header from ct0 cookie
        client.headers["x-csrf-token"] = self.ct0

        return client
        
    @classmethod
    async def load(cls, file_path: str = DEFAULT_ACCOUNT_FILE) -> 'Account | None':
        """
        Load account data from a JSON file.
        
        Args:
            file_path: Path to the account JSON file.
            
        Returns:
            An Account object if successful, None otherwise.
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"Account file not found: {path}")
            return None
            
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            logger.debug(f"Loaded account from {path}")
            return cls.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError, Exception) as e:
            logger.error(f"Failed to load account file {path}: {e}")
            return None
    
    async def save(self, file_path: str = DEFAULT_ACCOUNT_FILE):
        """
        Save the account data to a JSON file.
        
        Args:
            file_path: Path where to save the account data.
        """
        path = Path(file_path)
        # Create parent directories if they don't exist
        path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            data = self.to_dict()
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved account to {path}")
        except Exception as e:
            logger.error(f"Failed to save account to {path}: {e}")
            raise

    @classmethod
    async def create_or_update(cls, username: str, auth_token: str, ct0: str, 
                              user_agent: str = None, file_path: str = DEFAULT_ACCOUNT_FILE) -> 'Account':
        """
        Create a new account or update an existing one and save it to file.
        
        Args:
            username: Twitter/X username
            auth_token: The auth_token cookie value
            ct0: The ct0 cookie value
            user_agent: Optional user agent string
            file_path: Where to save the account data
            
        Returns:
            The created or updated Account object
        """
        account = Account(
            username=username,
            auth_token=auth_token,
            ct0=ct0,
            user_agent=user_agent or UserAgent().chrome
        )
        
        await account.save(file_path)
        logger.info(f"Account '{username}' saved to {file_path}")
        return account