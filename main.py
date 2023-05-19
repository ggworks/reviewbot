from fastapi import FastAPI, Request
import hmac
import hashlib
import requests

import openai

import os
import logging
import logging.config
cwd = os.path.dirname(__file__)
log_config = f"{cwd}/log.ini"
logging.config.fileConfig(log_config, disable_existing_loggers=False)

logger = logging.getLogger(__name__)

app = FastAPI()


SECRET_TOKEN = "helloworld"
OPENAI_API_KEY = os.getenv("API_KEY")
GITLAB_API_TOKEN =  os.getenv("GITLAB_API_TOKEN")
GITLAB_API_ORIGIN =  os.getenv("GITLAB_API_ORIGIN")


openai.api_key = OPENAI_API_KEY


def get_diff(project_id, commit_id):
    commit_url = f"{GITLAB_API_ORIGIN}/api/v4/projects/{project_id}/repository/commits/{commit_id}/diff"
    headers = {
        "PRIVATE-TOKEN": GITLAB_API_TOKEN
    }
    response = requests.get(commit_url, headers=headers)
    diffs = response.json()
    # diffs will be a list of changes, you might need to format it properly
    return diffs


@app.post("/gitlab-webhook")
async def gitlab_webhook(request: Request):

    # Verify signature
    signature = request.headers.get("X-Gitlab-Token")
    body = await request.body()
    # expected_signature = hmac.new(SECRET_TOKEN.encode(), body, hashlib.sha256).hexdigest()
    # if not hmac.compare_digest(expected_signature, signature):
    #     return {"message": "Invalid signature"}

    # Process webhook
    data = await request.json()
    for commit in data.get('commits', []):
        message = commit.get('message')
        diff = get_diff(data['project']['id'], commit['id'])
        logger.info(f"Commit message: {message}")

        # Send code to OpenAI for review
        model = "gpt-3.5-turbo"  # You can use other models
        messages = [{"role": "system", "content": "You are a helpful code assistant."},
                    {"role": "user", "content": f"Review this git code commit: \n```python\n{diff}\n```"}]
        response = openai.ChatCompletion.create(
        model=model,
        messages=messages
        )

        review = response['choices'][0]['message']['content']
        logger.info(f"Review: {review}")

        # Add review as a comment to the commit
        project_id = data['project']['id']
        commit_id = commit['id']
        comment_url = f"{GITLAB_API_ORIGIN}/api/v4/projects/{project_id}/repository/commits/{commit_id}/comments"
        comment_data = {
            "note": review
        }
        headers = {
            "PRIVATE-TOKEN": GITLAB_API_TOKEN
        }
        response = requests.post(comment_url, json=comment_data, headers=headers)

        if response.status_code != 201:
            logger.error(f"Failed to add comment to commit: {response.text}")

    # Return success message
    return {"message": "Webhook received and processed successfully"}
