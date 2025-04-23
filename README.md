# twitter-user-timeline-scraper

A practical tool to fetch recent tweets from a list of Twitter usernames and save them as JSON files. You provide a list of usernames, and the script downloads their latest tweets and some user metadata for each, storing the results in an `output/` folder.

## What does it do?
- Reads Twitter usernames from `target_accounts.txt` (one username per line).
- Uses your own Twitter session cookies (auth tokens) to fetch tweets from those accounts.
- Saves each user's tweets and metadata as separate JSON files in the `output/` directory.

## What does the output look like?
- For each username, you get two files:
  - `tweets_<username>_<timestamp>.json`: List of tweets (with content, date, tweet ID, etc).
  - `user_metadata_<username>_<timestamp>.json`: Basic info about the user and scrape details.

Example tweet output (truncated):
```json
[
  {
    "id_str": "1234567890",
    "user": { "username": "example", "displayname": "Example User" },
    "date": "2024-06-01T12:34:56",
    "rawContent": "This is a tweet!",
    "url": "https://twitter.com/example/status/1234567890"
  },
  ...
]
```

## Setup & Usage
1. **Clone this repo**
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Create a `.env` file** in the project root with your Twitter auth tokens:
   ```env
   TW_AUTH_TOKEN=your_auth_token_here
   TW_CT0_TOKEN=your_ct0_token_here
   ```
   (See the script or README comments for how to get these from your browser.)
   
   Optionally, you can set the delay (in seconds) between processing each account by adding this line to your `.env` file:
   ```env
   DELAY_BETWEEN_ACCOUNTS=1.5
   ```
   (Default is 1 second if not set. Increase this if you want to slow down requests.)
4. **Add target usernames** to `target_accounts.txt` (one per line, no @ needed).
5. **Run the script:**
   ```bash
   python main.py
   ```
6. **Check the `output/` folder** for your results.

## Notes
- This script does not use the official Twitter API. It requires your own session cookies.
- For personal/educational use only. Do not use for spamming, scraping at scale, or violating Twitter's terms of service.

---
**Disclaimer:** This project is for educational and personal research purposes only. You are responsible for how you use it. The author is not liable for any misuse. 