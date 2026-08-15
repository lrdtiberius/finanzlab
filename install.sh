#!/usr/bin/env sh
set -eu

docker compose build
docker compose up -d

echo "Haushaltsplaner läuft unter http://localhost:8798"

