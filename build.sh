#!/usr/bin/env bash
# exit on error
set -o errexit

echo "Installing system dependencies for WeasyPrint..."

# Forza la pulizia delle liste apt bloccate
echo "Cleaning up apt cache..."
rm -rf /var/lib/apt/lists/*
apt-get clean

# Ora esegui l'update e l'installazione
echo "Updating apt and installing dependencies..."
apt-get update -y
apt-get install -y libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libgobject-2.0-0

# Installa le tue librerie Python
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Build complete."