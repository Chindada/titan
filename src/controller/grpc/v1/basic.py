import grpc
from panther.basic import basic_pb2, basic_pb2_grpc, future_pb2, option_pb2, stock_pb2

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

    def GetFutureHistoryKbar(self, request: basic_pb2.HistoryKbarRequest, context):
        try:
            return self.agent.future_kbars(request.code, request.start, request.end)
        except Exception as e:
            context.set_code(grpc.StatusCode.ABORTED)
            context.set_details(str(e))
            return basic_pb2.HistoryKbarList()

    def GetStockVolumeRank(self, request: basic_pb2.VolumeRankRequest, context: grpc.ServicerContext):
        try:
            return self.agent.get_stock_volume_rank_by_date(
                count=10,
                date=request.date,
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.ABORTED)
            context.set_details(str(e))
            return basic_pb2.StockVolumeRankList()
