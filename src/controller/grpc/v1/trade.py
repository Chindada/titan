from queue import ShutDown

import grpc
from google.protobuf import empty_pb2
from panther.trade import trade_pb2, trade_pb2_grpc

from agent.agent import Agent


class RPCTrade(trade_pb2_grpc.TradeInterfaceServicer):
    def __init__(
        self,
        agent: Agent,
    ):
        self.agent = agent

    def SubscribeTrade(self, request, context):
        queue = self.agent.get_order_queue()
        if queue is None:
            return
        try:
            while True:
                event = queue.get(block=True)
                yield event
        except ShutDown:
            pass

    def UpdateAndPublishTrade(self, request, context):
        self.agent.update_order_non_block()
        return empty_pb2.Empty()

    def GetTradeByOrderID(self, request: trade_pb2.QueryTradeRequest, context: grpc.ServicerContext):
        order_id = request.order_id
        order = self.agent.get_local_order_by_order_id(order_id)
        if order is None:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"{order_id} not found.")
            return trade_pb2.Trade()
        return self.agent.post_process_order(order)
