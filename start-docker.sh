#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f .env ]; then
  echo "Using .env file from project root"
else
  echo ".env file not found. Copying from .env.example"
  cp .env.example .env
fi

docker compose -f backend/docker-compose.yml up -d

echo ""
echo "Docker services are running."
echo "- Redis: localhost:${REDIS_PORT:-6379}"
echo "- PostgreSQL: localhost:${POSTGRES_PORT:-5432}"
echo ""
echo "To stop services:"
echo "  docker compose -f backend/docker-compose.yml down"
