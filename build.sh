#!/usr/bin/env bash
# exit on error
set -o errexit

echo "Installing system dependencies for WeasyPrint (running as root)..."

# Pulisci la cache (SENZA sudo)
echo "Cleaning apt cache..."
apt-get clean

# Aggiorna e installa (SENZA sudo)
echo "Updating apt and installing dependencies..."
apt-get update -y
apt-get install -y libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libgobject-2.0-0

# I requisiti Python (non hanno mai avuto bisogno di sudo)
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Build complete."