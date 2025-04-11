# Usa un'immagine Python leggera
FROM python:3.11-slim

# Setta la directory di lavoro
WORKDIR /app

# Copia i file locali nella directory di lavoro nel container
COPY . .

# Installa le dipendenze
RUN pip install --no-cache-dir -r requirements.txt

# Espone la porta per Flask
EXPOSE 8080

# Comando per far partire il bot
CMD ["python", "main.py"]
