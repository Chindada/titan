import os

from prometheus_client import start_http_server

from agent.agent import Agent
from config.config import Config
from controller.grpc.server import GRPCServer
from logger import logger


def prometheus():
    listen_port = 6666
    if os.environ.get("PROMETHEUS_PORT") is not None and int(str(os.environ.get("PROMETHEUS_PORT"))) > 0:
        listen_port = int(str(os.environ.get("PROMETHEUS_PORT")))
    start_http_server(listen_port)
    logger.info("Prometheus started at port %d", listen_port)


def grpc_port():
    if os.environ.get("GRPC_PORT") is not None and int(str(os.environ.get("GRPC_PORT"))) > 0:
        return str(os.environ.get("GRPC_PORT"))
    return "56666"


if __name__ == "__main__":
    try:
        prometheus()
        cfg = Config.from_yaml("data/config.yaml")
        agent = Agent()
        agent.login(cfg.shioaji_auth, is_main=True)
        GRPCServer(agent=agent).serve_sync(grpc_port())
    except (Exception, BaseException) as e:
        if str(e) != "":
            logger.error(str(e))
