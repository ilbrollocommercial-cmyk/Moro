FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg nodejs ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
RUN useradd -m flux && chown -R flux:flux /app
USER flux
ENV FLUX_WEB=1 PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 8 --timeout 120 app:app"]
