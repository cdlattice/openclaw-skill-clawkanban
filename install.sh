#!/bin/bash

# This script initializes the ClawKanban system in the user's OpenClaw workspace.
# It ensures the tasks.json file and recovery directory are correctly set up.

# Get the OpenClaw workspace path, defaulting if not set
OPENCLAW_WORKSPACE=${OPENCLAW_WORKSPACE:-~/.openclaw/workspace}

KANBAN_FILE="$OPENCLAW_WORKSPACE/tasks.json"
RECOVERY_DIR="$OPENCLAW_WORKSPACE/memory"
RECOVERY_FILE="$RECOVERY_DIR/kanban_recovery.md"
SCHEMA_URL="https://openclaw.io/v1/kanban.schema.json"

echo "ClawKanban: Initializing workspace at $OPENCLAW_WORKSPACE..."

# Create the memory directory if it doesn't exist
mkdir -p "$RECOVERY_DIR"
if [ $? -ne 0 ]; then
    echo "ClawKanban: ERROR: Could not create recovery directory $RECOVERY_DIR."
    exit 1
fi

# Initialize tasks.json if it doesn't exist
if [ ! -f "$KANBAN_FILE" ]; then
    echo "ClawKanban: Creating initial tasks.json..."
    JSON_CONTENT='{
  "$schema": "'$SCHEMA_URL'",
  "metadata": {
    "last_sync": "'$(date -u +"%Y-%m-%dT%H:%M:%S.%6NZ")'",
    "version": 1
  },
  "tasks": []
}'
    echo "$JSON_CONTENT" > "$KANBAN_FILE"
    if [ $? -ne 0 ]; then
        echo "ClawKanban: ERROR: Could not create tasks.json at $KANBAN_FILE."
        exit 1
    fi
else
    echo "ClawKanban: tasks.json already exists. Skipping initialization."
fi

# Create recovery file if it doesn't exist (or just touch it)
if [ ! -f "$RECOVERY_FILE" ]; then
    echo "ClawKanban: Creating kanban_recovery.md..."
    touch "$RECOVERY_FILE"
    if [ $? -ne 0 ]; then
        echo "ClawKanban: ERROR: Could not create recovery file at $RECOVERY_FILE."
        exit 1
    fi
else
    echo "ClawKanban: kanban_recovery.md already exists. Skipping creation."
fi

echo "ClawKanban: Initialization complete."

