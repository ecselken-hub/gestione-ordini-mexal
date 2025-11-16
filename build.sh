#!/usr/bin/env bash
# exit on error
set -o errexit

echo "Installing system dependencies for WeasyPrint (with sudo)..."

# Pulisci la cache (con sudo)
echo "Cleaning apt cache (with sudo)..."
sudo apt-get clean

# Aggiorna e installa (con sudo)
echo "Updating apt and installing dependencies (with sudo)..."
sudo apt-get update -y
sudo apt-get install -y libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libgobject-2.0-0

# I requisiti Python NON hanno bisogno di sudo
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Build complete."