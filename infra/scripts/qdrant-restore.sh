#!/usr/bin/env bash
# Restore runbook companion to infra/kubernetes/apps/qdrant/base/backup-cronjob.yaml —
# docs/aws-architecture.md §9 promises "a documented restore runbook"; this is it.
#
# Usage: qdrant-restore.sh <bucket> <collection> <s3-key> [namespace]
# List available snapshots first with:
#   aws s3 ls s3://<bucket>/<collection>/
set -euo pipefail

BUCKET="${1:?bucket}"
COLLECTION="${2:?collection}"
S3_KEY="${3:?s3 key, e.g. 2026-11-09-<snapshot-file>}"
NAMESPACE="${4:-bceao-rag}"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

echo "Downloading s3://$BUCKET/$S3_KEY ..."
aws s3 cp "s3://$BUCKET/$S3_KEY" "$TMP"

echo "Uploading snapshot into the running qdrant pod and restoring ..."
kubectl -n "$NAMESPACE" cp "$TMP" "qdrant-0:/tmp/restore.snap"
kubectl -n "$NAMESPACE" exec qdrant-0 -- \
  curl -sf -X PUT \
    "http://localhost:6333/collections/$COLLECTION/snapshots/upload?priority=snapshot" \
    -F "snapshot=@/tmp/restore.snap"

echo "Done. Verify with:"
echo "  kubectl -n $NAMESPACE exec qdrant-0 -- curl -s http://localhost:6333/collections/$COLLECTION"
