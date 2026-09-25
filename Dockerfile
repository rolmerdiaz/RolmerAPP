FROM python:3.10-slim

# Instalar dependencias necesarias y Chromium / ChromeDriver desde los repositorios oficiales de Linux
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libgconf-2-4 \
    libasound2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
