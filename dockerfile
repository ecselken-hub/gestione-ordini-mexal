# 1. Partiamo dall'immagine Python 3.11 STABILE (Bookworm)
FROM python:3.11-slim-bookworm

# Imposta la cartella di lavoro all'interno del server
WORKDIR /app

# 2. Aggiorna Linux e installa le dipendenze di WeasyPrint (come root)
# Questo è l'equivalente del tuo build.sh
RUN apt-get update -y && apt-get install -y \
    libpango-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libgobject-2.0-0 \
    --no-install-recommends \
# Pulisci la cache di apt per ridurre le dimensioni
&& rm -rf /var/lib/apt/lists/*