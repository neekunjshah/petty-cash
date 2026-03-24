#!/bin/bash
# Seed the Docker volume with migrated SQLite data
# Run after first deploy: bash seed-data.sh
#
# Requires: the container to be running (deployed via Coolify)

set -e

CONTAINER=$(docker ps --filter "name=pettycash" --format '{{.Names}}' | head -1)

if [ -z "$CONTAINER" ]; then
    echo "Error: pettycash container not running"
    exit 1
fi

echo "=== Seeding PettyCash data ==="

# Create directories in volume
docker exec "$CONTAINER" mkdir -p /app/data/signatures

# Copy SQLite database into container's data volume
docker cp instance/pettycash.db "$CONTAINER:/app/data/pettycash.db"

# Restart to pick up the data
docker restart "$CONTAINER"

echo "Data seeded successfully!"
echo "Verify at: https://pettycash.nysatex.com"
