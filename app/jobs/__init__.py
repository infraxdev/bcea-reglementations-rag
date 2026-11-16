"""Crawl/ingest job dispatch and tracking.

The API submits jobs via `runtime.submit()`. Depending on JOB_QUEUE_BACKEND they either
run in the API process (inprocess) or go to SQS for `python -m app.worker` (sqs). Either
way the same `runner.execute()` runs them and records status in the state stores, so
GET /crawl/{id}/status and GET /ingest/{id}/progress work from any API replica.
"""
