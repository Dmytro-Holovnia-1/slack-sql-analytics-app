FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN --network=host pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY init_db ./init_db
COPY README.md ./README.md

CMD ["python", "-m", "app.main"]
