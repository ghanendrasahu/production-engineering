FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY producer.py worker.py ./
RUN groupadd --system app && useradd --system --gid app app \
    && mkdir -p /app && chown -R app:app /app
USER app
