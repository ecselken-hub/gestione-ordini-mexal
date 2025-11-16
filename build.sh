#!/usr/bin/env bash
# exit on error
set -o errexit

# 1. Aggiorna i pacchetti di Linux e installa le dipendenze di sistema per GTK3/WeasyPrint
echo "Installing system dependencies for WeasyPrint..."
apt-get update -y
apt-get install -y libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libgobject-2.0-0

# 2. Installa le tue librerie Python
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Build complete."