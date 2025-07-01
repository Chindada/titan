ARG PYTHON_VERSION=3.13.5

FROM python:${PYTHON_VERSION}-slim AS builder
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends \
    build-essential \
    ssh \
    git \
    dumb-init \
    tzdata \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt-get/lists/*
COPY requirements.txt .
RUN mkdir -p ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts
RUN --mount=type=ssh \
    pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

FROM python:${PYTHON_VERSION}-slim AS runtime
ENV TZ=Asia/Taipei \
    ROOT_PATH=/usr/share/app
ENV SJ_LOG_PATH=${ROOT_PATH}/titan/logs/shioaji.log
ENV SJ_CONTRACTS_PATH=${ROOT_PATH}/titan/data
RUN mkdir -p \
    ${ROOT_PATH}/titan \
    ${ROOT_PATH}/titan/logs \
    ${ROOT_PATH}/titan/data
WORKDIR ${ROOT_PATH}/titan
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt requirements.txt
COPY --from=builder /usr/bin/dumb-init /usr/bin/dumb-init
COPY pfx pfx
COPY scripts scripts
COPY src src
RUN pip install --no-cache /wheels/*
ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["bash", "-c" ,"/usr/share/app/titan/scripts/docker-entrypoint.sh"]
