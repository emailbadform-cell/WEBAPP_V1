FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8000
CMD ["sh", "-c", "mkdir -p /app/options-feed-data && python -u options_feed.py --venue both --interval 15 --out /app/options-feed-data & exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
