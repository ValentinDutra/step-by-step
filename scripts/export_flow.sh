#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Export the current Langflow flow as JSON backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="flows/backups"
mkdir -p "$BACKUP_DIR"

if [ -f flows/dev_pipeline.json ]; then
    cp flows/dev_pipeline.json "$BACKUP_DIR/dev_pipeline_${TIMESTAMP}.json"
    echo "Flow backed up to $BACKUP_DIR/dev_pipeline_${TIMESTAMP}.json"
else
    echo "No flow file found at flows/dev_pipeline.json"
    echo "Export from Langflow UI first: Download JSON -> save to flows/dev_pipeline.json"
fi
