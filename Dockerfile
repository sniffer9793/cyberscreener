FROM python:3.11-slim

WORKDIR /app

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ .

# Create DB directory with persistent volume
RUN mkdir -p /data/db

# Set DB path to persistent volume
ENV DB_PATH=/data/db/cyberscreener.db

EXPOSE 8000

# Run scheduler in background + API server
CMD sh -c "python scheduler.py --daemon --interval 7200 & uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"
