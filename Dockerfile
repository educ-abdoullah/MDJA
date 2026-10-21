FROM python:3.12-slim AS dependencies
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY --from=dependencies /wheels /wheels
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r /tmp/requirements.txt \
    && rm -rf /wheels /tmp/requirements.txt \
    && groupadd --gid 10001 gazette \
    && useradd --uid 10001 --gid gazette --no-create-home gazette \
    && mkdir -p /app/data/raw /app/articles_bruts \
    && chown -R gazette:gazette /app/data /app/articles_bruts
COPY src ./src
COPY sources.csv .
COPY infra/bootstrap.py ./infra/bootstrap.py
COPY infra/migrations ./infra/migrations
USER gazette
ENTRYPOINT ["python", "-m", "gazette"]

FROM runtime AS test
USER root
COPY requirements-dev.txt requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
COPY dags ./dags
COPY infra ./infra
COPY bin ./bin
USER gazette
ENTRYPOINT ["python", "infra/check.py"]

FROM runtime AS app
