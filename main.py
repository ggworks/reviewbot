from fastapi import FastAPI, Request
import hmac
import hashlib

import sys
import os
import logging
import logging.config
cwd = os.path.dirname(__file__)
log_config = f"{cwd}/log.ini"
logging.config.fileConfig(log_config, disable_existing_loggers=False)

logger = logging.getLogger(__name__)

sys.path.append('')

app = FastAPI()

SECRET_TOKEN = "helloworld"


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

    logger.info(data)
    # Do something with data...

    # Return success message
    return {"message": "Webhook received and processed successfully"}
