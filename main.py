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

from lsp_utils.lsp_process import LspProcess
import lsp_utils.lsp as lsp

logger.info(f"TEST_APP: {TEST_APP}")


def get_file_changes(repo_full_name, sha):
    commit_url = f"https://api.github.com/repos/{repo_full_name}/commits/{sha}"
    headers = {
        "Authorization": f"Bearer {GITHUB_API_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    response = requests.get(commit_url, headers=headers)
    commit_data = response.json()
    return commit_data['files']  # Github includes diff in the commit data


def post_comment(repo_full_name, sha, filename, review, position, line):

    commemt = f"#### *Auto Review*:\n`{filename}`\n#### *review*:\n{review}"
    commit_url = f"https://api.github.com/repos/{repo_full_name}/commits/{sha}/comments"
    comment_data = {
        "body": commemt,
        "path": filename,
        "position": position,
        "line": line
    }
    headers = {
        "Authorization": f"Bearer {GITHUB_API_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    response = requests.post(commit_url, json=comment_data, headers=headers)

    if response.status_code != 201:
        logger.error(f"Failed to add comment to commit: {response.text}")


def review_patch_and_comment(repo_full_name, sha, file_change):
    filename = file_change["filename"]
    patch = file_change["patch"]

    review = chat.get_review_for_patch(patch, filename)
    if not review:
        return

    if TEST_APP:
        logger.info(f"Review: {review}")
        return

    post_comment(repo_full_name, sha, filename, review, file_change['changes'], file_change['patch'].count("\n") + 1)


def review_changes_and_comment(repo_full_name, sha, file_change, line_ranges, symbols, file_content):
    # todo:
    for line_range in line_ranges:
        symbol_paths = utils.get_symbols_intersecting_with_range(symbols, line_range)
        # print(f"\nrange {line_range} ....")

        for symbol_path in symbol_paths:
            # print(f"path:--")
            for s in symbol_path:
                print(f"    {s['name']}, {lsp.SYMBOL_KIND_STR_LIST[s['kind']]}")


def process_source_file(repo_full_name, sha, file_change, language_type, language_server_path, args=[]):
    filename = file_change["filename"]
    patch = file_change["patch"]

    lsp_porcess = LspProcess()
    if not lsp_porcess.start_server(language_server_path, args):
        logger.error(f"start_server {language_server_path} failed")
        return None, None, None

    root_path = os.path.join(os.path.dirname(__file__), "temp")

    if not lsp_porcess.initialize("."):
        logger.error("lsp init failed")
        lsp_porcess.stop_server()
        return None, None, None

    file_content = utils.download_file(repo_full_name, filename, sha)
    temp_file = os.path.join(root_path, os.path.basename(filename))

    with open(temp_file, 'w') as file:
        file.write(file_content)

    lsp_porcess.open_file(temp_file, language_type, file_content)
    symbols = lsp_porcess.get_symbols(temp_file)

    lsp_porcess.stop_server()
    os.remove(temp_file)

    if not symbols:
        logger.error("get symbols failed")
        return None, None, None

    line_ranges = utils.parse_diff(patch)
    return symbols, file_content, line_ranges


def review_and_comment(repo_full_name, sha, file_change):
    filename = file_change["filename"]
    if utils.should_skip_review(filename):
        logger.info(f"Skipping review for {filename}")
        return

    language_type = utils.get_language_type(filename)
    patch = file_change["patch"]
    if TEST_APP:
        logger.info(f"filename:\n {filename}\n")
        logger.info(f"patch:\n {patch}\n")

    # language_server_path = config.lang_server.get(language_type, None)

    language_server_path = None
    if language_server_path:
        args = []
        if language_type == 'typescript':
            args = ['--stdio']
        symbols, file_content, line_ranges = process_source_file(
            repo_full_name, sha, file_change, language_type, language_server_path, args)
        if not symbols:
            logger.error("get symbols failed")
            return review_patch_and_comment(repo_full_name, sha, file_change)

        review_changes_and_comment(repo_full_name, sha, file_change, line_ranges, symbols, file_content)
    else:
        return review_patch_and_comment(repo_full_name, sha, file_change)


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

        file_changes = get_file_changes(data['repository']['full_name'], commit_id)
        for file_change in file_changes:
            background_tasks.add_task(review_and_comment, data['repository']['full_name'], commit_id, file_change)

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

    review = chat.get_review_for_patch(diff["diff"], filename)
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
