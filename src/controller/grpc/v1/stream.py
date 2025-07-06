from queue import ShutDown

import grpc
import shioaji as sj
from panther.stream import stream_pb2, stream_pb2_grpc

from agent.agent import Agent


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
            return stream_pb2.ShioajiEvent()

    def SubscribeStockQuote(self, request: stream_pb2.SubscribeRequest, context: grpc.ServicerContext):
        if request.code == "":
            return
        try:
            self.agent.subscribe_stock_quote(request.code)
        except Exception as e:
            context.set_code(grpc.StatusCode.ABORTED)
            context.set_details(str(e))
            return stream_pb2.StockQuote()
        queue = self.agent.get_stock_quote_queue(request.code)
        if queue is None:
            return
        try:
            while True:
                quote: sj.QuoteSTKv1 = queue.get(block=True)
                yield stream_pb2.StockQuote(
                    code=quote.code,
                    date_time=str(quote.datetime),
                    open=quote.open,
                    avg_price=quote.avg_price,
                    close=quote.close,
                    high=quote.high,
                    low=quote.low,
                    amount=quote.amount,
                    total_amount=quote.total_amount,
                    volume=quote.volume,
                    total_volume=quote.total_volume,
                    tick_type=quote.tick_type,
                    chg_type=quote.chg_type,
                    price_chg=quote.price_chg,
                    pct_chg=quote.pct_chg,
                    bid_side_total_vol=quote.bid_side_total_vol,
                    ask_side_total_vol=quote.ask_side_total_vol,
                    bid_side_total_cnt=quote.bid_side_total_cnt,
                    ask_side_total_cnt=quote.ask_side_total_cnt,
                    closing_oddlot_shares=quote.closing_oddlot_shares,
                    closing_oddlot_close=quote.closing_oddlot_close,
                    closing_oddlot_amount=quote.closing_oddlot_amount,
                    closing_oddlot_bid_price=quote.closing_oddlot_bid_price,
                    closing_oddlot_ask_price=quote.closing_oddlot_ask_price,
                    fixed_trade_vol=quote.fixed_trade_vol,
                    fixed_trade_amount=quote.fixed_trade_amount,
                    bid_price=quote.bid_price,
                    bid_volume=quote.bid_volume,
                    diff_bid_vol=quote.diff_bid_vol,
                    ask_price=quote.ask_price,
                    ask_volume=quote.ask_volume,
                    diff_ask_vol=quote.diff_ask_vol,
                    avail_borrowing=quote.avail_borrowing,
                    suspend=quote.suspend,
                    simtrade=quote.simtrade,
                )
        except ShutDown:
            return stream_pb2.StockQuote()

    def SubscribeFutureTick(self, request: stream_pb2.SubscribeRequest, context: grpc.ServicerContext):
        if request.code == "":
            return
        try:
            self.agent.subscribe_future_tick(request.code)
        except Exception as e:
            context.set_code(grpc.StatusCode.ABORTED)
            context.set_details(str(e))
            return stream_pb2.FutureTick()
        queue = self.agent.get_tick_queue(request.code)
        if queue is None:
            return
        try:
            while True:
                tick = queue.get(block=True)
                yield stream_pb2.FutureTick(
                    code=tick.code,
                    date_time=str(tick.datetime),
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
            return stream_pb2.FutureTick()

    def SubscribeFutureBidAsk(self, request: stream_pb2.SubscribeRequest, context: grpc.ServicerContext):
        if request.code == "":
            return
        try:
            self.agent.subscribe_future_bidask(request.code)
        except Exception as e:
            context.set_code(grpc.StatusCode.ABORTED)
            context.set_details(str(e))
            return stream_pb2.FutureBidAsk()
        queue = self.agent.get_bidask_queue(request.code)
        if queue is None:
            return
        try:
            while True:
                bidask = queue.get(block=True)
                yield stream_pb2.FutureBidAsk(
                    code=bidask.code,
                    date_time=str(bidask.datetime),
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
            return stream_pb2.FutureBidAsk()

    def GetSnapshot(self, request: stream_pb2.SnapshotRequest, context: grpc.ServicerContext):
        try:
            codes: list[str] = []
            if request.codes:
                for code in request.codes:
                    codes.append(code)
            if request.type == stream_pb2.SnapshotRequestType.SNAPSHOT_REQUEST_TYPE_UNKNOWN:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Unknown snapshot request type")
                return stream_pb2.SnapshotMap()
            if len(codes) == 0:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("No codes provided for snapshot request")
                return stream_pb2.SnapshotMap()
            elif request.type == stream_pb2.SnapshotRequestType.SNAPSHOT_REQUEST_TYPE_STOCK:
                return self.agent.snapshots_stocks(codes)
            elif request.type == stream_pb2.SnapshotRequestType.SNAPSHOT_REQUEST_TYPE_FUTURE:
                return self.agent.snapshots_futures(codes)
        except Exception as e:
            context.set_code(grpc.StatusCode.ABORTED)
            context.set_details(str(e))
            return stream_pb2.SnapshotMap()
