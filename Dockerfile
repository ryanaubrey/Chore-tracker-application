FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    CHORES_HOST=0.0.0.0 CHORES_DB=/data/chores.sqlite3 \
    CHORES_REQUIRE_DATA_MOUNT=1
WORKDIR /app
RUN groupadd --gid 1000 chores \
    && useradd --uid 1000 --gid 1000 --no-create-home chores \
    && install -d -o chores -g chores /data
COPY backend/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY alembic.ini ./
COPY scripts/backup_sqlite.py scripts/healthcheck.py ./scripts/
USER chores
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "scripts/healthcheck.py"]
CMD ["python", "-m", "backend.wsgi"]
