import threading
from concurrent import futures

import grpc
from panther.basic import basic_pb2_grpc
from panther.health import health_pb2_grpc
from panther.stream import stream_pb2_grpc

from agent.agent import Agent
from controller.grpc.v1 import basic, health, stream
from logger import logger


class GRPCServer:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.thead_pool = futures.ThreadPoolExecutor(1024)
        self.srv = grpc.server(self.thead_pool)

        self._stop_lock: threading.Lock = threading.Lock()
        self.stopped = False

        health_pb2_grpc.add_HealthInterfaceServicer_to_server(
            health.RPCHealth(
                stop_function=self.stop,
            ),
            self.srv,
        )
        basic_pb2_grpc.add_BasicInterfaceServicer_to_server(basic.RPCBasic(agent=self.agent), self.srv)
        stream_pb2_grpc.add_StreamInterfaceServicer_to_server(stream.RPCStream(agent=self.agent), self.srv)

    def stop(self):
        with self._stop_lock:
            if self.stopped:
                return
            self.stopped = True
        logger.info("Stopping gRPC Server...")
        self.agent.logout()
        self.srv.stop(grace=None)
        self.thead_pool.shutdown(wait=False, cancel_futures=True)
        logger.info("gRPC Server is stopped")

    def serve_sync(self, port: str):
        try:
            self.srv.add_insecure_port(f"[::]:{port}")
            self.srv.start()
            logger.info("gRPC Server started at port %s", port)
            self.srv.wait_for_termination()
        except (Exception, BaseException):
            self.stop()
