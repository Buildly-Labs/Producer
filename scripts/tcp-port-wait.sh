#!/bin/bash
# Wait for a TCP port to be available
# Usage: tcp-port-wait.sh HOST PORT [TIMEOUT]

set -e

HOST=${1:-localhost}
PORT=${2:-5432}
TIMEOUT=${3:-30}

echo "Waiting for $HOST:$PORT to be available..."

for i in $(seq 1 $TIMEOUT); do
    if nc -z "$HOST" "$PORT" > /dev/null 2>&1; then
        echo "$HOST:$PORT is available after $i seconds"
        exit 0
    fi
    echo "Waiting for $HOST:$PORT... ($i/$TIMEOUT)"
    sleep 1
done

echo "Timeout waiting for $HOST:$PORT"
exit 1