from fastapi import FastAPI, BackgroundTasks, Request
import hmac
import hashlib
import requests
import json
from dotenv import load_dotenv
load_dotenv('./env/.env.cr.local')
import openai

import os
import logging
import logging.config

cwd = os.path.dirname(__file__)
log_config = f"{cwd}/log.ini"
logging.config.fileConfig(log_config, disable_existing_loggers=False)

logger = logging.getLogger(__name__)

app = FastAPI()

OPENAI_API_KEY = os.getenv("API_KEY")
OPENAI_API_PROXY = os.getenv("API_PROXY", None)

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
GITHUB_API_TOKEN = os.getenv("GITHUB_API_TOKEN")

GITLAB_API_TOKEN = os.getenv("GITLAB_API_TOKEN")
GITLAB_API_ORIGIN = os.getenv("GITLAB_API_ORIGIN")
GITLAB_WEBHOOK_SECRET = os.getenv("GITLAB_WEBHOOK_SECRET")


openai.api_key = OPENAI_API_KEY
openai.proxy = OPENAI_API_PROXY


def get_review(patch):
    if type(patch) != str:
        patch = json.dumps(patch)

    prompt = f"""
    Review the commit provided for quality, logic, and security,  commit patch: \n{patch}\n
    """

    model = "gpt-3.5-turbo"
    messages = [{"role": "system", "content": "You are a helpful Code Reviewer."},
                {"role": "user", "content": prompt}]

    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages
        )
        review = response['choices'][0]['message']['content']
        return review

    except openai.error.Timeout as e:
        logger.error(f"OpenAI request timed out: {e}")
    except openai.error.APIConnectionError as e:
        logger.error(f"OpenAI API connection error: {e}")
    except openai.error.InvalidRequestError as e:
        logger.error(f"OpenAI invalid request error: {e}")


def get_diff(repo_full_name, sha):
    commit_url = f"https://api.github.com/repos/{repo_full_name}/commits/{sha}"
    headers = {
        "Authorization": f"Bearer {GITHUB_API_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    response = requests.get(commit_url, headers=headers)
    commit_data = response.json()
    diffs = commit_data['files']  # Github includes diff in the commit data
    return diffs


def review_and_comment(repo_full_name, sha, diff):

    review = get_review(diff["patch"])
    if not review:
        return

    filename = diff["filename"]

    commemt = f"*Auto Review*:\n`{filename}`\n*review*:\n{review}"
    commit_url = f"https://api.github.com/repos/{repo_full_name}/commits/{sha}/comments"
    comment_data = {
        "body": commemt,
        "path": filename,
        "position": diff['changes'],
        "line": diff['patch'].count("\n") + 1
    }
    headers = {
        "Authorization": f"Bearer {GITHUB_API_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    response = requests.post(commit_url, json=comment_data, headers=headers)

    if response.status_code != 201:
        logger.error(f"Failed to add comment to commit: {response.text}")


@app.post("/github-webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):

    # Verify signature
    signature = request.headers.get("X-Hub-Signature-256")
    body = await request.body()
    expected_signature = "sha256=" + hmac.new(GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        logger.error(f"Invalid signature")
        return {"message": "Invalid signature"}

    # Process webhook
    data = await request.json()
    for commit in data.get('commits', []):
        diffs = get_diff(data['repository']['full_name'], commit['id'])
        for diff in diffs:
            background_tasks.add_task(review_and_comment, data['repository']['full_name'], commit["id"], diff)

    # Return success message
    return {"message": "Webhook received and processed successfully"}


def get_gitlab_diff(project_id, commit_id):
    commit_url = f"{GITLAB_API_ORIGIN}/api/v4/projects/{project_id}/repository/commits/{commit_id}/diff"
    headers = {
        "Authorization": f"Bearer {GITLAB_API_TOKEN}"
    }
    response = requests.get(commit_url, headers=headers)
    diffs = response.json()
    return diffs


def review_and_comment_gitlab(project_id, commit_id, diff):
    review = get_review(diff["diff"])
    if not review:
        return

    filename = diff["old_path"]
    comment = f"*Auto Review*:\n\n`{filename}`\n\n*review*:\n\n{review}"
    commit_url = f"{GITLAB_API_ORIGIN}/api/v4/projects/{project_id}/repository/commits/{commit_id}/comments"
    comment_data = {
        "note": comment,
    }
    headers = {
        "Authorization": f"Bearer {GITLAB_API_TOKEN}"
    }
    response = requests.post(commit_url, json=comment_data, headers=headers)

    if response.status_code != 201:
        logger.error(f"Failed to add comment to commit: {response.text}")


@app.post("/gitlab-webhook")
async def gitlab_webhook(request: Request, background_tasks: BackgroundTasks):

    # Verify signature
    signature = request.headers.get("X-Gitlab-Token")
    body = await request.body()
    expected_signature = hmac.new(GITLAB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        logger.error(f"Invalid signature")
        return {"message": "Invalid signature"}

    # Process webhook
    data = await request.json()
    for commit in data.get('commits', []):
        diffs = get_gitlab_diff(data['project']['id'], commit['id'])
        for diff in diffs:
            background_tasks.add_task(review_and_comment_gitlab, data['project']['id'], commit["id"], diff)

    # Return success message
    return {"message": "Webhook received and processed successfully"}
