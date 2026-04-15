FROM python:3.14-slim

WORKDIR /app

# I-install ang system dependencies (kailangan lang ang ffmpeg)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# I-copy at i-install ang Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# I-copy ang source code
COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]