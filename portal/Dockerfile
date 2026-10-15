FROM python:3.13-slim
WORKDIR /opt/portal
COPY pyproject.toml ./
COPY xrt_portal ./xrt_portal
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home portal && mkdir -p /data/state /data/releases && chown -R portal:portal /data
USER portal
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn","xrt_portal.main:app","--host","0.0.0.0","--port","8001","--no-access-log"]
