from google.protobuf import empty_pb2
from grpc import RpcError
from panther.health import health_pb2_grpc


class RPCHealth(health_pb2_grpc.HealthInterfaceServicer):
    def __init__(
        self,
        stop_function=None,
    ):
        self.stop_function = stop_function

    def HealthChannel(self, request_iterator, _):
        try:
            for _ in request_iterator:
                yield empty_pb2.Empty()
        except (RpcError, Exception, BaseException):
            self.stop_function()
