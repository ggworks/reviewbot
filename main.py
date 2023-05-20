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


def should_skip_review(filename):
    # list of file extensions for which review should be skipped
    skip_extensions = ['.txt', '.json', '.xml', '.csv', '.md', '.log', '.ini', '.yml', '.pyc', '.class']

    asset_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.eot', '.ttf', '.woff', '.woff2']

    # list of file names to be skipped
    skip_files = ['README.md', 'LICENSE', '.gitignore', 'package-lock.json', 'yarn.lock', 'Makefile', 'Dockerfile']

    # list of folders to be skipped
    skip_folders = ['__pycache__', '.git', '.vscode', 'node_modules', 'dist', 'build']

    # get file extension
    file_extension = os.path.splitext(filename)[-1]

    # get file name
    file_name = os.path.basename(filename)

    # check if the file is in a skip folder
    for folder in skip_folders:
        if folder in filename.split(os.path.sep):
            return True

    # check if file extension is in the skip list
    if file_extension in skip_extensions or file_name in skip_files:
        return True

    if file_extension in asset_extensions:
        return True

    return False


def get_review(patch, filename):
    if type(patch) != str:
        patch = json.dumps(patch)

    # logger.info(f"filename:\n {filename}\n")
    # logger.info(f"Patch:\n {patch}\n")

    sys_prompt = """
As a Code Reviewer, your task is to assist users in reviewing their git commit diffs with a focus on four aspects: code score, quality, logic, and security. Your comments will be sent to GitHub, so make sure to provide meaningful and useful feedback. If there are no significant observations to add, simply return "no issue".

Please structure your reply in the following four parts in markdown format:

"Code Score": Provide a score between 1-10, reflecting the overall quality of the code including readability, conciseness, and efficiency.

"Quality": Give feedback on the code quality, if applicable. This might encompass the code's structure, style, and adherence to best practices. If there are no issues, reply with "no issue".

"Logic": Review the logic of the code. If applicable, provide recommendations for correctness or improvements in logic. If there are no issues, reply with "no issue".

"Security": Evaluate the security of the code, including potential vulnerabilities, security risks, or neglected security practices. If there are no issues, reply with "no issue".

    """

    prompt = f"commmit patch is:\n{patch}\n"

    model = "gpt-3.5-turbo"
    messages = [{"role": "system", "content": sys_prompt},
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
    except openai.error.RateLimitError as e:
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

    filename = diff["filename"]
    if should_skip_review(filename):
        logger.info(f"Skipping review for {filename}")
        return

    review = get_review(diff["patch"], filename)
    if not review:
        return

    # logger.info(f"Review: {review}"

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
        if '/no-cr' in message:
            logger.info(f"Skipping commit with '/no-cr' in: {message}, id: {commit['id']}")
            continue
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
    filename = diff["old_path"]

    review = get_review(diff["diff"], filename)
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
        diffs = get_gitlab_diff(data['project']['id'], commit['id'])
        for diff in diffs:
            background_tasks.add_task(review_and_comment_gitlab, data['project']['id'], commit["id"], diff)

    # Return success message
    return {"message": "Webhook received and processed successfully"}
