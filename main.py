from fastapi import FastAPI, BackgroundTasks, Request
import hmac
import hashlib
import requests
import json
import config
from config import *
import os
import logging
import logging.config

cwd = os.path.dirname(__file__)
log_config = f"{cwd}/log.ini"
logging.config.fileConfig(log_config, disable_existing_loggers=False)

logger = logging.getLogger(__name__)

app = FastAPI()

from cr_db import cr_db
import utils

import chat

logger.info(f"TEST_APP: {TEST_APP}")

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
    filename = diff["filename"]
    if utils.should_skip_review(filename):
        logger.info(f"Skipping review for {filename}")
        return

    patch = diff["patch"]
    if TEST_APP:
        logger.info(f"filename:\n {filename}\n")
        logger.info(f"Patch:\n {patch}\n")

    review = chat.get_review(patch, filename)
    if not review:
        return

    if TEST_APP:
        logger.info(f"Review: {review}")
        return

    commemt = f"#### *Auto Review*:\n`{filename}`\n#### *review*:\n{review}"
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
        message = commit['message']
        commit_id = commit['id']
        if '/no-cr' in message:
            logger.info(f"Skipping commit with '/no-cr' in: {message}, id: {commit_id}")
            continue
        
        if cr_db.get_reviewed_commit(commit_id, "github"):
            logger.info(f"Skipping commit already reviewed: {commit_id}")
            continue
        
        diffs = get_diff(data['repository']['full_name'], commit_id)
        for diff in diffs:
            background_tasks.add_task(review_and_comment, data['repository']['full_name'], commit_id, diff)
            
        cr_db.add_reviewed_commit(commit_id, data['repository']['full_name'], "github")

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
    filename = diff["old_path"]

    review = chat.get_review(diff["diff"], filename)
    if not review:
        return

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
    if not signature or signature != GITLAB_WEBHOOK_SECRET:
        logger.error(f"Invalid signature")
        return {"message": "Invalid signature"}

    body = await request.body()
    # expected_signature = hmac.new(GITLAB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    # if not hmac.compare_digest(expected_signature, signature):
    #     logger.error(f"Invalid signature")
    #     return {"message": "Invalid signature"}

    # Process webhook
    data = await request.json()
    for commit in data.get('commits', []):
        commit_id = commit['id']
        diffs = get_gitlab_diff(data['project']['id'], commit['id'])
        if cr_db.get_reviewed_commit(commit_id, "gitlab"):
            logger.info(f"Skipping commit already reviewed: {commit_id}")
            continue
        for diff in diffs:
            background_tasks.add_task(review_and_comment_gitlab, data['project']['id'], commit["id"], diff)
            
        cr_db.add_reviewed_commit(commit_id, data['project']['id'], "gitlab")

    # Return success message
    return {"message": "Webhook received and processed successfully"}
