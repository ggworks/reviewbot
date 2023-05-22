from pymongo import MongoClient
import config
from config import MONGO_URL

from datetime import datetime


class CodeReviewDB(object):
    def __init__(self):
        self.client = MongoClient(MONGO_URL, tz_aware=True)
        self.db = self.client.reviewbot
        self.reviewed_commits = self.db["reviewed_commits"]
        self.reviewed_commits.create_index([("commit_id", 1), ("source", 1), ("repo", 1)], unique=True)

    def add_reviewed_commit(self, commit_id: str, repo: str, source: str):
        self.reviewed_commits.insert_one(
            {"commit_id": commit_id,
             "repo": repo,
             "source": source,
             "created_at": datetime.utcnow(),
             "update_at": datetime.utcnow()})

    def get_reviewed_commit(self, commit_id: str, source: str):
        return self.reviewed_commits.find_one({"commit_id": commit_id, "source": source})


cr_db = CodeReviewDB()
