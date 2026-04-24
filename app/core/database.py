from functools import lru_cache

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.core.settings import Settings, get_settings


@lru_cache(maxsize=1)
def get_mongo_client() -> MongoClient:
    settings = get_settings()
    return MongoClient(settings.mongodb_uri, tz_aware=True)


def get_database(settings: Settings | None = None) -> Database:
    runtime_settings = settings or get_settings()
    return get_mongo_client()[runtime_settings.mongodb_database]


def get_pull_request_collection(settings: Settings | None = None) -> Collection:
    runtime_settings = settings or get_settings()
    return get_database(runtime_settings)[runtime_settings.mongodb_pr_collection]
