from panther.basic import basic_pb2_grpc, future_pb2, option_pb2, stock_pb2

from agent.agent import Agent


class RPCBasic(basic_pb2_grpc.BasicInterfaceServicer):
    def __init__(
        self,
        agent: Agent,
    ):
        self.agent = agent

    def GetAllStockDetail(self, request, _):
        return stock_pb2.StockDetailList(list=self.agent.get_all_stocks())

    def GetAllFutureDetail(self, request, _):
        return future_pb2.FutureDetailList(list=self.agent.get_all_futures())

    def GetAllOptionDetail(self, request, _):
        return option_pb2.OptionDetailList(list=self.agent.get_all_options())
