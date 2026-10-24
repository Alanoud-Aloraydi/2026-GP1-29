# Build one non-root application image for the HTTP API and evaluation worker.
FROM python:3.14-slim AS dependencies
WORKDIR /build
RUN python -m venv /opt/venv
COPY requirements.txt pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip /opt/venv/bin/pip install -r requirements.txt
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip /opt/venv/bin/pip install --no-deps .

FROM python:3.14-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENBLAS_NUM_THREADS=1 \
    XDG_DATA_HOME=/var/lib/harass
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 harass \
    && useradd --uid 10001 --gid harass --create-home harass \
    && mkdir -p /app /var/lib/harass/dbdata /var/lib/harass/.pyrit_cache \
    && chown -R harass:harass /app /var/lib/harass
COPY --from=dependencies /opt/venv /opt/venv
WORKDIR /app
COPY --chown=harass:harass frontend ./frontend
COPY --chown=harass:harass config ./config
COPY --chown=harass:harass data ./data
USER harass
EXPOSE 8000
CMD ["python", "-m", "harass.bootstrap.api"]
