# 1. Partiamo dall'immagine Python 3.11 STABILE (Bookworm)
FROM python:3.11-slim-bookworm

# Imposta la cartella di lavoro all'interno del server
WORKDIR /app

# 2. Aggiorna Linux e installa le dipendenze di WeasyPrint (come root)
RUN apt-get update -y && apt-get install -y \
    libpango-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libgobject-2.0-0 \
    --no-install-recommends \
# Pulisci la cache di apt per ridurre le dimensioni
&& rm -rf /var/lib/apt/lists/*

# 3. Copia e installa i requisiti Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copia il resto della tua app
COPY . .

# 5. Dici a Render quale comando eseguire per avviare il server
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:$PORT", "--workers", "4"]