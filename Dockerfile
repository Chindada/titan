FROM python:3.13.5-slim
ENV TZ=Asia/Taipei \
    ROOT_PATH=/usr/share/app
ENV SJ_LOG_PATH=${ROOT_PATH}/titan/logs/shioaji.log
ENV SJ_CONTRACTS_PATH=${ROOT_PATH}/titan/data
RUN apt update -y \
    && apt install -y --no-install-recommends \
    build-essential \
    ssh \
    git \
    dumb-init \
    tzdata \
    && apt autoremove -y \
    && apt clean \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p \
    ${ROOT_PATH}/titan \
    ${ROOT_PATH}/titan/logs \
    ${ROOT_PATH}/titan/data
WORKDIR ${ROOT_PATH}/titan
COPY requirements.txt requirements.txt
COPY pfx pfx
COPY scripts scripts
COPY src src
RUN mkdir -p ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts
RUN --mount=type=ssh \
    pip install -r requirements.txt
ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["bash", "-c" ,"/usr/share/app/titan/scripts/docker-entrypoint.sh"]
