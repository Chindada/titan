from datetime import datetime
from queue import ShutDown

from panther.stream import stream_pb2, stream_pb2_grpc

from agent.agent import Agent

DATE_TIME_FORMAT: str = "%Y-%m-%d %H:%M:%S.%f"


class RPCStream(stream_pb2_grpc.StreamInterfaceServicer):
    def __init__(
        self,
        agent: Agent,
    ):
        self.agent = agent

    def SubscribeShioajiEvent(self, request, context):
        queue = self.agent.get_event_queue()
        if queue is None:
            return
        try:
            while True:
                event = queue.get(block=True)
                yield event
        except ShutDown:
            pass

    def SubscribeFutureTick(self, request: stream_pb2.SubscribeFutureRequest, _):
        if request.code == "":
            return
        result = self.agent.subscribe_future_tick(request.code)
        if result is not None:
            return
        queue = self.agent.get_tick_queue(request.code)
        if queue is None:
            return
        try:
            while True:
                tick = queue.get(block=True)
                yield stream_pb2.FutureTick(
                    code=tick.code,
                    date_time=datetime.strftime(tick.datetime, DATE_TIME_FORMAT),
                    open=tick.open,
                    underlying_price=tick.underlying_price,
                    bid_side_total_vol=tick.bid_side_total_vol,
                    ask_side_total_vol=tick.ask_side_total_vol,
                    avg_price=tick.avg_price,
                    close=tick.close,
                    high=tick.high,
                    low=tick.low,
                    amount=tick.amount,
                    total_amount=tick.total_amount,
                    volume=tick.volume,
                    total_volume=tick.total_volume,
                    tick_type=tick.tick_type,
                    chg_type=tick.chg_type,
                    price_chg=tick.price_chg,
                    pct_chg=tick.pct_chg,
                    simtrade=tick.simtrade,
                )
        except ShutDown:
            pass

    def SubscribeFutureBidAsk(self, request: stream_pb2.SubscribeFutureRequest, _):
        if request.code == "":
            return
        result = self.agent.subscribe_future_bidask(request.code)
        if result is not None:
            return
        queue = self.agent.get_bidask_queue(request.code)
        if queue is None:
            return
        try:
            while True:
                bidask = queue.get(block=True)
                yield stream_pb2.FutureBidAsk(
                    code=bidask.code,
                    date_time=datetime.strftime(bidask.datetime, DATE_TIME_FORMAT),
                    bid_total_vol=bidask.bid_total_vol,
                    ask_total_vol=bidask.ask_total_vol,
                    simtrade=bidask.simtrade,
                    bid_price=bidask.bid_price,
                    bid_volume=bidask.bid_volume,
                    diff_bid_vol=bidask.diff_bid_vol,
                    ask_price=bidask.ask_price,
                    ask_volume=bidask.ask_volume,
                    diff_ask_vol=bidask.diff_ask_vol,
                    first_derived_bid_price=bidask.first_derived_bid_price,
                    first_derived_ask_price=bidask.first_derived_ask_price,
                    first_derived_bid_vol=bidask.first_derived_bid_vol,
                    first_derived_ask_vol=bidask.first_derived_ask_vol,
                    underlying_price=bidask.underlying_price,
                )
        except ShutDown:
            pass
