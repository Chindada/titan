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
                trade = queue.get(block=True)
                yield trade
        except ShutDown:
            return trade_pb2.Trade()

    def UpdateAndPublishTrade(self, request, context: grpc.ServicerContext):
        try:
            self.agent.update_order_non_block()
            return empty_pb2.Empty()
        except Exception as e:
            context.set_code(grpc.StatusCode.ABORTED)
            context.set_details(str(e))
            return empty_pb2.Empty()

    def GetTradeByOrderID(self, request: trade_pb2.QueryTradeRequest, context: grpc.ServicerContext):
        order_id = request.order_id
        order = self.agent.get_local_order_by_order_id(order_id)
        if order is None:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"{order_id} not found.")
            return trade_pb2.Trade()
        return self.agent.trade_to_pb(order)

    def BuyFuture(self, request: trade_pb2.BaseOrder, context: grpc.ServicerContext):
        try:
            return self.agent.buy_future(
                request.code,
                request.price,
                request.quantity,
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.ABORTED)
            context.set_details(str(e))
            return trade_pb2.Trade()

    def SellFuture(self, request: trade_pb2.BaseOrder, context: grpc.ServicerContext):
        try:
            return self.agent.sell_future(
                request.code,
                request.price,
                request.quantity,
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.ABORTED)
            context.set_details(str(e))
            return trade_pb2.Trade()

    def SellFirstFuture(self, request: trade_pb2.BaseOrder, context: grpc.ServicerContext):
        try:
            return self.agent.sell_first_future(
                request.code,
                request.price,
                request.quantity,
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.ABORTED)
            context.set_details(str(e))
            return trade_pb2.Trade()

    def CancelTrade(self, request: trade_pb2.Trade, context: grpc.ServicerContext):
        try:
            return self.agent.cancel_future(
                request.order_id,
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.ABORTED)
            context.set_details(str(e))
            return trade_pb2.Trade()

    def GetFuturePosition(self, request, context):
        try:
            return self.agent.list_future_positions()
        except Exception as e:
            context.set_code(grpc.StatusCode.ABORTED)
            context.set_details(str(e))
            return trade_pb2.FuturePositionList()

    def GetMargin(self, request, context):
        try:
            return self.agent.margin()
        except Exception as e:
            context.set_code(grpc.StatusCode.ABORTED)
            context.set_details(str(e))
            return trade_pb2.Margin()
