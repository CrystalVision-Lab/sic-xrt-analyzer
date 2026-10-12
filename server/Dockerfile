FROM python:3.13-slim AS runtime
WORKDIR /opt/xrt
COPY server/pyproject.toml /tmp/xrt-server-dependencies.toml
RUN python -c "import subprocess,sys,tomllib; deps=tomllib.load(open('/tmp/xrt-server-dependencies.toml','rb'))['project']['dependencies']; subprocess.check_call([sys.executable,'-m','pip','install','--no-cache-dir',*deps])" && useradd --uid 10001 --create-home xrt && mkdir -p /data/assets && chown -R xrt:xrt /data
COPY pyproject.toml README.md ./
COPY src ./src
COPY server ./server
RUN pip install --no-cache-dir --no-deps . ./server
USER xrt
ENV PYTHONUNBUFFERED=1
CMD ["sh", "-c", "alembic -c server/alembic.ini upgrade head && uvicorn xrt_server.main:app --host 0.0.0.0 --port 8000 --no-access-log"]

FROM runtime AS testing
USER root
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pytest
USER xrt
FROM runtime AS production
