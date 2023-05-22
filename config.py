import os
from dotenv import load_dotenv
load_dotenv('./env/.env.cr.local')

OPENAI_API_KEY = os.getenv("API_KEY")
OPENAI_API_PROXY = os.getenv("API_PROXY", None)

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
GITHUB_API_TOKEN = os.getenv("GITHUB_API_TOKEN")

GITLAB_API_TOKEN = os.getenv("GITLAB_API_TOKEN")
GITLAB_API_ORIGIN = os.getenv("GITLAB_API_ORIGIN")
GITLAB_WEBHOOK_SECRET = os.getenv("GITLAB_WEBHOOK_SECRET")


MONGO_URL = os.getenv("MONGO_URL")

TEST_APP = os.getenv("TEST_APP") == "true"