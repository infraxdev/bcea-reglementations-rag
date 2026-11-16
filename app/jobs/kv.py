"""Tiny key-value stores for job state: one JSON document per job_id.

- MemoryKV: a dict in this process (JOB_STATE_BACKEND=memory, inprocess queue only).
- DynamoKV: a DynamoDB table with hash key `job_id` and the document in `data`
  (JOB_STATE_BACKEND=dynamodb). Tables come from infra/terraform/modules/data on AWS;
  locally (DynamoDB Local) they're created on first use when JOB_STATE_CREATE_TABLES=true.

Both are synchronous. Callers on the event loop accept the ~10 ms DynamoDB round trip;
the API wraps its calls in asyncio.to_thread.
"""

from __future__ import annotations

import json
import threading
from typing import Protocol

from ..config import JobSettings


class KVStore(Protocol):
    def get(self, key: str) -> dict | None: ...
    def put(self, key: str, value: dict) -> None: ...


class MemoryKV:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> dict | None:
        with self._lock:
            raw = self._data.get(key)
        return json.loads(raw) if raw is not None else None

    def put(self, key: str, value: dict) -> None:
        raw = json.dumps(value)
        with self._lock:
            self._data[key] = raw


class DynamoKV:
    def __init__(self, table_name: str, settings: JobSettings) -> None:
        import boto3

        self._table_name = table_name
        self._client = boto3.client(
            "dynamodb", endpoint_url=settings.dynamodb_endpoint_url, region_name=settings.aws_region
        )
        if settings.create_tables:
            self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            self._client.describe_table(TableName=self._table_name)
            return
        except self._client.exceptions.ResourceNotFoundException:
            pass
        try:
            self._client.create_table(
                TableName=self._table_name,
                KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
        except self._client.exceptions.ResourceInUseException:
            pass  # another process (api vs worker) created it first
        self._client.get_waiter("table_exists").wait(TableName=self._table_name)

    def get(self, key: str) -> dict | None:
        resp = self._client.get_item(
            TableName=self._table_name, Key={"job_id": {"S": key}}, ConsistentRead=True
        )
        item = resp.get("Item")
        return json.loads(item["data"]["S"]) if item else None

    def put(self, key: str, value: dict) -> None:
        self._client.put_item(
            TableName=self._table_name,
            Item={"job_id": {"S": key}, "data": {"S": json.dumps(value)}},
        )


_stores: dict[str, KVStore] = {}
_stores_lock = threading.Lock()


def get_store(name: str) -> KVStore:
    """`name` is "jobs" (crawl job status) or "progress" (ingest progress)."""
    from ..config import get_job_settings

    with _stores_lock:
        store = _stores.get(name)
        if store is None:
            settings = get_job_settings()
            if settings.state_backend == "dynamodb":
                table = settings.jobs_table if name == "jobs" else settings.progress_table
                store = DynamoKV(table, settings)
            else:
                store = MemoryKV()
            _stores[name] = store
        return store
