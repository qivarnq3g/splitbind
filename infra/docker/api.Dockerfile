ARG PYTHON_BASE_IMAGE=python:3.11.9-slim-bookworm@sha256:8fb099199b9f2d70342674bd9dbccd3ed03a258f26bbd1d556822c6dfc60c317
FROM ${PYTHON_BASE_IMAGE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv

RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /src
COPY research/python/constraints-py311.txt research/python/pyproject.toml /src/research/python/
COPY research/python/src /src/research/python/src
COPY services/api/constraints-py311.txt services/api/pyproject.toml /src/services/api/
COPY services/api/config /src/services/api/config
COPY services/api/splitbind /src/services/api/splitbind
RUN python -m pip install \
      --constraint /src/services/api/constraints-py311.txt \
      /src/research/python \
      '/src/services/api[demo]' \
      'gunicorn==23.0.0'

ARG PYTHON_BASE_IMAGE
FROM ${PYTHON_BASE_IMAGE} AS runtime

ENV ENVIRONMENT=production \
    PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SPLITBIND_ALGORITHM_CONTRACTS=/app/contracts/algorithm

RUN groupadd --gid 10001 splitbind \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin splitbind

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app/services/api
COPY --chown=10001:10001 services/api/manage.py ./manage.py
COPY --chown=10001:10001 services/api/config ./config
COPY --chown=10001:10001 services/api/splitbind ./splitbind
COPY --chown=10001:10001 contracts/algorithm /app/contracts/algorithm
COPY --chmod=0555 infra/docker/api-entrypoint.sh /usr/local/bin/api-entrypoint.sh
COPY --chmod=0555 infra/docker/worker-entrypoint.sh /usr/local/bin/worker-entrypoint.sh

USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/api-entrypoint.sh"]
