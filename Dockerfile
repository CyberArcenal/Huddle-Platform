# Dockerfile
FROM python:3.10-slim

# 1. I-set ang working directory
WORKDIR /app

# 2. Kopyahin ang dependencies at i-install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Kopyahin ang buong source code
COPY . .

# 4. I-export ang port at default command para sa development
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]