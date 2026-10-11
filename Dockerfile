FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
# A mainland host pulls the default index at a few kB/s, so the index is a build
# argument and deployment sets it to a local mirror.
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/

RUN addgroup --system app && adduser --system --group app --home /app
# The SQLite file lives here and the container does not run as root, so the
# directory has to belong to that user before anything opens a database in it.
RUN mkdir -p /app/backend/data && chown -R app:app /app
USER app

WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
