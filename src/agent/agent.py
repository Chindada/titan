import logging
import os
import threading
from datetime import datetime, timedelta
from queue import Queue, ShutDown
from typing import List

import shioaji as sj
import shioaji.constant as sc
import shioaji.position as sp
from google.protobuf import timestamp_pb2
from panther.basic import basic_pb2, future_pb2, option_pb2, stock_pb2
from panther.stream import stream_pb2
from panther.trade import trade_pb2
from shioaji.contracts import Contract, Future, Option, Stock
from shioaji.order import Trade

from config.auth import ShioajiAuth
from logger import logger

logging.getLogger("shioaji").propagate = False


def get_is_simulation() -> bool:
    sim = False
    if (
        os.environ.get("SHIOAJI_SIMULATION") is not None
        and str(os.environ.get("SHIOAJI_SIMULATION")).strip().lower() == "true"
    ):
        sim = True
    if sim is True:
        logger.info("Shioaji is running in simulation mode")
    else:
        logger.info("Shioaji is running in real mode")
    return sim


class Agent:
    max_subscribe_count = 200
    current_subscribe_count = 0

    def __init__(self):
        self.__api = sj.Shioaji(simulation=get_is_simulation())
        self.__login_progess = int()
        self.__login_status_lock = threading.Lock()

        # order map with lock
        # key is order_id
        self.__order_map: dict[str, Trade] = {}
        self.__order_map_lock = threading.Lock()
        self.__non_block_update_order_lock = threading.Lock()

        # stock, future, option code map
        self.stock_map: dict[str, Contract] = {}
        self.stock_map_lock = threading.Lock()
        self.future_map: dict[str, Contract] = {}
        self.future_map_lock = threading.Lock()
        self.option_map: dict[str, Contract] = {}
        self.option_map_lock = threading.Lock()

        # subscribe
        self.sub_lock = threading.Lock()
        self.tick_sub_dict: dict[str, Contract] = {}
        self.bidask_sub_dict: dict[str, Contract] = {}
        self.__tick_queue_map: dict[str, Queue] = {}
        self.__bidask_queue_map: dict[str, Queue] = {}

        self.__event_queue: Queue = Queue()
        self.__order_queue: Queue = Queue()

    def event_callback(self, resp_code: int, event_code: int, info: str, event: str):
        self.__event_queue.put(
            stream_pb2.ShioajiEvent(
                resp_code=resp_code,
                event_code=event_code,
                info=info,
                event=event,
            )
        )
        logger.info("event: %d/%d/%s/%s", resp_code, event_code, info, event)

    def exract_order_timestamp(self, order: Trade) -> timestamp_pb2.Timestamp:
        if order.status.order_datetime is None:
            order.status.order_datetime = datetime.now()
            logger.warning("Order %s has no order_datetime, set to now", order.status.id)
        if order.status.order_datetime.hour <= 5 and order.status.order_datetime.hour >= 0:
            if order.status.order_datetime.day != datetime.now().day:
                order.status.order_datetime = order.status.order_datetime + timedelta(days=1)
        return timestamp_pb2.Timestamp(
            seconds=int(order.status.order_datetime.timestamp()),
            nanos=int((order.status.order_datetime.timestamp() - int(order.status.order_datetime.timestamp())) * 1e9),
        )

    def exract_order_type(self, order: Trade) -> trade_pb2.OrderType:
        order_type = trade_pb2.OrderType.TYPE_UNKNOWN
        if order.contract.security_type == sc.SecurityType.Stock:
            if order.order.order_lot in (sj.order.StockOrderLot.Odd, sj.order.StockOrderLot.IntradayOdd):
                order_type = trade_pb2.OrderType.TYPE_STOCK_SHARE
            else:
                order_type = trade_pb2.OrderType.TYPE_STOCK_LOT
        elif order.contract.security_type == sc.SecurityType.Future:
            order_type = trade_pb2.OrderType.TYPE_FUTURE
        return order_type

    def exract_order_action(self, order: Trade) -> trade_pb2.OrderAction:
        order_action = trade_pb2.OrderAction.ORDER_ACTION_UNKNOWN
        if order.order.action == sc.Action.Buy:
            order_action = trade_pb2.OrderAction.ORDER_ACTION_BUY
        elif order.order.action == sc.Action.Sell:
            order_action = trade_pb2.OrderAction.ORDER_ACTION_SELL
        return order_action

    def exract_order_status(self, order: Trade) -> trade_pb2.Trade:
        order_status = trade_pb2.OrderStatus.ORDER_STATUS_UNKNOWN
        if order.status.status == sc.Status.Cancelled:
            order_status = trade_pb2.OrderStatus.ORDER_STATUS_CANCELLED
        elif order.status.status == sc.Status.Filled:
            order_status = trade_pb2.OrderStatus.ORDER_STATUS_FILLED
        elif order.status.status == sc.Status.PartFilled:
            order_status = trade_pb2.OrderStatus.ORDER_STATUS_PART_FILLED
        elif order.status.status == sc.Status.Inactive:
            order_status = trade_pb2.OrderStatus.ORDER_STATUS_INACTIVE
        elif order.status.status == sc.Status.Failed:
            order_status = trade_pb2.OrderStatus.ORDER_STATUS_FAILED
        elif order.status.status == sc.Status.PendingSubmit:
            order_status = trade_pb2.OrderStatus.ORDER_STATUS_PENDING_SUBMIT
        elif order.status.status == sc.Status.PreSubmitted:
            order_status = trade_pb2.OrderStatus.ORDER_STATUS_PRE_SUBMITTED
        elif order.status.status == sc.Status.Submitted:
            order_status = trade_pb2.OrderStatus.ORDER_STATUS_SUBMITTED
        return order_status

    def exract_order_price(self, order: Trade):
        order_price = order.order.price
        if order.status.modified_price != 0:
            order_price = order.status.modified_price
        return order_price

    def trade_to_pb(self, order: Trade) -> trade_pb2.Trade:
        return trade_pb2.Trade(
            type=self.exract_order_type(order),
            code=order.contract.code,
            order_id=order.order.id,
            action=self.exract_order_action(order),
            price=self.exract_order_price(order),
            quantity=order.order.quantity,
            filled_quantity=order.status.deal_quantity,
            status=self.exract_order_status(order),
            order_time=self.exract_order_timestamp(order),
        )

    def non_block_order_callback(self, reply: list[sj.order.Trade]):
        with self.__non_block_update_order_lock:
            threads = []

            def put(order: Trade):
                self.__order_queue.put(self.trade_to_pb(order))

            for order in reply:
                t = threading.Thread(target=put, daemon=True, args=(order,))
                threads.append(t)
                t.start()
            for t in threads:
                t.join()

    def update_order_non_block(self):
        self.__api.update_status(timeout=0, cb=self.non_block_order_callback)

    def update_local_order(self):
        with self.__order_map_lock:
            cache = self.__order_map.copy()
            self.__order_map = {}
            try:
                self.__api.update_status()
                for order in self.__api.list_trades():
                    self.__order_map[order.order.id] = order
                    self.__order_queue.put(self.trade_to_pb(order))
            except Exception:
                self.__order_map = cache

    def order_callback(self, order_state: sc.OrderState, res: dict):
        self.update_local_order()  # every time order callback, update local order
        if order_state in (sc.OrderState.FuturesOrder, sc.OrderState.StockOrder):
            if res["contract"]["code"] is None:
                logger.error("place order code is none")
                return
            logger.info(
                "%s order: %s %s %.2f %d %s",
                str(res["operation"]["op_type"]).lower(),
                res["contract"]["code"],
                res["order"]["action"],
                res["order"]["price"],
                res["order"]["quantity"],
                res["order"]["id"],
            )
        elif order_state in (sc.OrderState.FuturesDeal, sc.OrderState.StockDeal):
            if res["code"] is None:
                logger.error("deal order code is none")
                return
            logger.info(
                "deal order: %s %s %.2f %d %s",
                res["code"],
                res["action"],
                res["price"],
                res["quantity"],
                res["trade_id"],
            )

    def login_cb(self, security_type: sc.SecurityType):
        with self.__login_status_lock:
            if security_type.value in [item.value for item in sc.SecurityType]:
                self.__login_progess += 1
                logger.info("login progress: %d/4, %s", self.__login_progess, security_type)

    def login(self, auth: ShioajiAuth):
        logger.info("Shioaji version: %s", self.get_sj_version())
        self.__api.quote.set_event_callback(self.event_callback)
        self.__api.quote.set_on_tick_fop_v1_callback(self.future_tick_callback)
        self.__api.quote.set_on_bidask_fop_v1_callback(self.future_bid_ask_callback)
        self.__api.login(
            api_key=auth.api_key,
            secret_key=auth.api_key_secret,
            contracts_cb=self.login_cb,
            subscribe_trade=True,
        )
        while True:
            with self.__login_status_lock:
                if self.__login_progess == 4:
                    break
        self.__api.activate_ca(
            ca_path=f"./pfx/{auth.ca_path}",
            ca_passwd=auth.ca_password,
            person_id=auth.person_id,
        )
        self.fill_stock_map()
        self.fill_future_map()
        self.fill_option_map()

        if self.__api.stock_account.signed is False or self.__api.futopt_account.signed is False:
            raise RuntimeError("account not sign")
        self.__api.set_order_callback(self.order_callback)
        self.update_local_order()

        return self

    def logout(self):
        try:
            self.__event_queue.shutdown()
            self.__order_queue.shutdown()
            with self.sub_lock:
                for code in list(self.__tick_queue_map.keys()):
                    self.__tick_queue_map[code].shutdown()
                for code in list(self.__bidask_queue_map.keys()):
                    self.__bidask_queue_map[code].shutdown()
            self.__api.logout()
            logger.info("logout shioaji")
        except Exception:
            logger.error("logout shioaji fail")

    def get_usage(self):
        return self.__api.usage()

    def get_sj_version(self):
        return str(sj.__version__)

    def fill_stock_map(self):
        for contracts in self.__api.Contracts.Stocks:
            for contract in contracts:
                if contract.category == "00":
                    continue
                with self.stock_map_lock:
                    if isinstance(contract, Stock):
                        self.stock_map[contract.code] = contract

        with self.stock_map_lock:
            logger.info("total stock: %d", len(self.stock_map))

    def get_all_stocks(self) -> List[stock_pb2.StockDetail]:
        with self.stock_map_lock:
            return [
                stock_pb2.StockDetail(
                    category=contract.category,
                    code=code,
                    currency=contract.currency,
                    day_trade=contract.day_trade,
                    delivery_date=contract.delivery_date,
                    delivery_month=contract.delivery_month,
                    exchange=contract.exchange,
                    limit_down=contract.limit_down,
                    limit_up=contract.limit_up,
                    margin_trading_balance=contract.margin_trading_balance,
                    multiplier=contract.multiplier,
                    name=contract.name,
                    option_right=contract.option_right,
                    reference=contract.reference,
                    security_type=contract.security_type,
                    short_selling_balance=contract.short_selling_balance,
                    strike_price=contract.strike_price,
                    symbol=contract.symbol,
                    target_code=contract.target_code,
                    underlying_code=contract.underlying_code,
                    underlying_kind=contract.underlying_kind,
                    unit=contract.unit,
                    update_date=contract.update_date,
                )
                for code, contract in self.stock_map.items()
            ]

    def fill_future_map(self):
        for contracts in self.__api.Contracts.Futures:
            for contract in contracts:
                with self.future_map_lock:
                    if isinstance(contract, Future):
                        self.future_map[contract.code] = contract
            for contract in contracts:
                if "微型臺指" in contract.name:
                    logger.info("Found future: %s with code: %s", contract.name, contract.code)
                if "小型臺指" in contract.name:
                    logger.info("Found future: %s with code: %s", contract.name, contract.code)
                if "臺股期貨" in contract.name:
                    logger.info("Found future: %s with code: %s", contract.name, contract.code)
        with self.future_map_lock:
            logger.info("total future: %d", len(self.future_map))

    def get_all_futures(self) -> List[future_pb2.FutureDetail]:
        with self.future_map_lock:
            return [
                future_pb2.FutureDetail(
                    category=contract.category,
                    code=code,
                    currency=contract.currency,
                    day_trade=contract.day_trade,
                    delivery_date=contract.delivery_date,
                    delivery_month=contract.delivery_month,
                    exchange=contract.exchange,
                    limit_down=contract.limit_down,
                    limit_up=contract.limit_up,
                    margin_trading_balance=contract.margin_trading_balance,
                    multiplier=contract.multiplier,
                    name=contract.name,
                    option_right=contract.option_right,
                    reference=contract.reference,
                    security_type=contract.security_type,
                    short_selling_balance=contract.short_selling_balance,
                    strike_price=contract.strike_price,
                    symbol=contract.symbol,
                    target_code=contract.target_code,
                    underlying_code=contract.underlying_code,
                    underlying_kind=contract.underlying_kind,
                    unit=contract.unit,
                    update_date=contract.update_date,
                )
                for code, contract in self.future_map.items()
            ]

    def get_future_contract_by_code(self, code):
        with self.future_map_lock:
            if code in self.future_map:
                return self.future_map[code]
            else:
                return None

    def fill_option_map(self):
        for contracts in self.__api.Contracts.Options:
            for contract in contracts:
                with self.option_map_lock:
                    if isinstance(contract, Option):
                        self.option_map[contract.code] = contract
        with self.option_map_lock:
            logger.info("total option: %d", len(self.option_map))

    def get_all_options(self) -> List[option_pb2.OptionDetail]:
        with self.option_map_lock:
            return [
                option_pb2.OptionDetail(
                    category=contract.category,
                    code=code,
                    currency=contract.currency,
                    day_trade=contract.day_trade,
                    delivery_date=contract.delivery_date,
                    delivery_month=contract.delivery_month,
                    exchange=contract.exchange,
                    limit_down=contract.limit_down,
                    limit_up=contract.limit_up,
                    margin_trading_balance=contract.margin_trading_balance,
                    multiplier=contract.multiplier,
                    name=contract.name,
                    option_right=contract.option_right,
                    reference=contract.reference,
                    security_type=contract.security_type,
                    short_selling_balance=contract.short_selling_balance,
                    strike_price=contract.strike_price,
                    symbol=contract.symbol,
                    target_code=contract.target_code,
                    underlying_code=contract.underlying_code,
                    underlying_kind=contract.underlying_kind,
                    unit=contract.unit,
                    update_date=contract.update_date,
                )
                for code, contract in self.option_map.items()
            ]

    def subscribe_future_tick(self, code):
        with self.sub_lock:
            if code in self.tick_sub_dict:
                raise Exception(f"Already subscribed to future tick: {code}")
            if self.current_subscribe_count >= self.max_subscribe_count:
                raise Exception("Max subscribe count reached")
            contract = self.get_future_contract_by_code(code)
            if contract is None:
                raise Exception(f"Contract {code} not found")
            self.__api.quote.subscribe(
                contract,
                quote_type=sc.QuoteType.Tick,
                version=sc.QuoteVersion.v1,
            )
            self.current_subscribe_count += 1
            self.tick_sub_dict[code] = contract
            self.__tick_queue_map[code] = Queue()
            logger.info(
                "subscribe future tick %s %s",
                code,
                contract.name,
            )

    def subscribe_future_bidask(self, code):
        with self.sub_lock:
            if code in self.bidask_sub_dict:
                raise Exception(f"Already subscribed to future bidask: {code}")
            if self.current_subscribe_count >= self.max_subscribe_count:
                raise Exception("Max subscribe count reached")
            contract = self.get_future_contract_by_code(code)
            if contract is None:
                raise Exception(f"Contract {code} not found")
            self.__api.quote.subscribe(
                contract,
                quote_type=sc.QuoteType.BidAsk,
                version=sc.QuoteVersion.v1,
            )
            self.current_subscribe_count += 1
            self.bidask_sub_dict[code] = contract
            self.__bidask_queue_map[code] = Queue()
            logger.info(
                "subscribe future bidask %s %s",
                code,
                contract.name,
            )

    def unsubscribe_future_tick(self, code):
        with self.sub_lock:
            if code in self.tick_sub_dict:
                self.__api.quote.unsubscribe(
                    self.tick_sub_dict[code],
                    quote_type=sc.QuoteType.Tick,
                    version=sc.QuoteVersion.v1,
                )
                del self.tick_sub_dict[code]
                logger.info(
                    "unsubscribe future tick %s %s",
                    code,
                    self.get_future_contract_by_code(code).name,
                )
            else:
                raise Exception(f"Not subscribed to future tick: {code}")

    def future_tick_callback(self, _, tick: sj.TickFOPv1):
        try:
            self.__tick_queue_map[tick.code].put(tick)
        except ShutDown:
            return

    def future_bid_ask_callback(self, _, bidask: sj.BidAskFOPv1):
        try:
            self.__bidask_queue_map[bidask.code].put(bidask)
        except ShutDown:
            return

    def get_event_queue(self):
        return self.__event_queue

    def get_order_queue(self):
        return self.__order_queue

    def get_tick_queue(self, code: str):
        with self.sub_lock:
            return self.__tick_queue_map.get(code, None)

    def get_bidask_queue(self, code: str):
        with self.sub_lock:
            return self.__bidask_queue_map.get(code, None)

    def get_local_order_by_order_id(self, order_id: str):
        with self.__order_map_lock:
            return self.__order_map.get(order_id, None)

    def buy_future(self, code: str, price: float, quantity: int):
        return self.trade_to_pb(
            self.__api.place_order(
                contract=self.get_future_contract_by_code(code),
                order=self.__api.Order(
                    price=price,
                    quantity=quantity,
                    action=sc.Action.Buy,
                    price_type=sc.FuturesPriceType.LMT,
                    order_type=sc.OrderType.ROD,
                    octype=sc.FuturesOCType.Auto,
                    account=self.__api.futopt_account,
                ),
            )
        )

    def sell_future(self, code: str, price: float, quantity: int):
        return self.trade_to_pb(
            self.__api.place_order(
                contract=self.get_future_contract_by_code(code),
                order=self.__api.Order(
                    price=price,
                    quantity=quantity,
                    action=sc.Action.Sell,
                    price_type=sc.FuturesPriceType.LMT,
                    order_type=sc.OrderType.ROD,
                    octype=sc.FuturesOCType.Auto,
                    account=self.__api.futopt_account,
                ),
            )
        )

    def cancel_future(self, order_id: str):
        cancel_order = self.get_local_order_by_order_id(order_id)
        if cancel_order is None:
            return Exception(f"Order with ID {order_id} not found.")
        if cancel_order.status.status == sc.Status.Cancelled:
            return Exception(f"Order with ID {order_id} is already cancelled.")
        return self.trade_to_pb(self.__api.cancel_order(cancel_order))

    def future_kbars(self, code: str, start_date: str, end_date: str):
        kbars = self.__api.kbars(
            contract=self.get_future_contract_by_code(code),
            start=start_date,
            end=end_date,
        )
        response = basic_pb2.HistoryKbarList()
        total_count = len(kbars.ts)
        if kbars is None or total_count == 0:
            return response
        for pos in range(total_count):
            response.list.append(
                basic_pb2.HistoryKbar(
                    code=code,
                    kbar_time=timestamp_pb2.Timestamp(seconds=int(kbars.ts[pos] / 1e9)),
                    close=kbars.Close[pos],
                    open=kbars.Open[pos],
                    high=kbars.High[pos],
                    low=kbars.Low[pos],
                    volume=kbars.Volume[pos],
                )
            )
        return response

    def account_balance(self) -> sp.AccountBalance:
        return self.__api.account_balance()

    def exract_margin_status(self, status: sp.FetchStatus) -> trade_pb2.FetchStatus:
        if status is None:
            return trade_pb2.FETCH_STATUS_UNKNOWN
        elif status == sp.FetchStatus.Fetched:
            return trade_pb2.FETCH_STATUS_FETCHED
        elif status == sp.FetchStatus.Fetching:
            return trade_pb2.FETCH_STATUS_FETCHING
        elif status == sp.FetchStatus.Unfetch:
            return trade_pb2.FETCH_STATUS_UNFETCH

    def margin(self):
        margin = self.__api.margin(self.__api.futopt_account)
        return trade_pb2.Margin(
            status=self.exract_margin_status(margin.status),
            yesterday_balance=margin.yesterday_balance,
            today_balance=margin.today_balance,
            deposit_withdrawal=margin.deposit_withdrawal,
            fee=margin.fee,
            tax=margin.tax,
            initial_margin=margin.initial_margin,
            maintenance_margin=margin.maintenance_margin,
            margin_call=margin.margin_call,
            risk_indicator=margin.risk_indicator,
            royalty_revenue_expenditure=margin.royalty_revenue_expenditure,
            equity=margin.equity,
            equity_amount=margin.equity_amount,
            option_openbuy_market_value=margin.option_openbuy_market_value,
            option_opensell_market_value=margin.option_opensell_market_value,
            option_open_position=margin.option_open_position,
            option_settle_profitloss=margin.option_settle_profitloss,
            future_open_position=margin.future_open_position,
            today_future_open_position=margin.today_future_open_position,
            future_settle_profitloss=margin.future_settle_profitloss,
            available_margin=margin.available_margin,
            plus_margin=margin.plus_margin,
            plus_margin_indicator=margin.plus_margin_indicator,
            security_collateral_amount=margin.security_collateral_amount,
            order_margin_premium=margin.order_margin_premium,
            collateral_amount=margin.collateral_amount,
        )

    def list_future_positions(self):
        positions: List[sp.FuturePosition] = []
        positions = self.__api.list_positions(self.__api.futopt_account)
        result = trade_pb2.FuturePositionList()
        for pos in positions:
            action = trade_pb2.OrderAction.ORDER_ACTION_UNKNOWN
            if pos.direction == sc.ACTION_BUY:
                action = trade_pb2.OrderAction.ORDER_ACTION_BUY
            elif pos.direction == sc.ACTION_SELL:
                action = trade_pb2.OrderAction.ORDER_ACTION_SELL
            result.list.append(
                trade_pb2.FuturePosition(
                    id=pos.id,
                    code=pos.code,
                    direction=action,
                    quantity=pos.quantity,
                    price=pos.price,
                    last_price=pos.last_price,
                    pnl=pos.pnl,
                )
            )
        return result

    def list_stock_positions(self) -> List[sp.StockPosition]:
        result: List[sp.StockPosition] = self.__api.list_positions(
            self.__api.stock_account,
            unit=sc.Unit.Share,
        )
        return result

    def get_position_detail(self, detail_id: int) -> List[sp.StockPositionDetail | sp.FuturePositionDetail]:
        result: List[sp.StockPositionDetail | sp.FuturePositionDetail] = self.__api.list_position_detail(
            self.__api.stock_account,
            detail_id,
        )
        return result

    def settlements(self):
        return self.__api.settlements(self.__api.stock_account)

    def get_stock_volume_rank_by_date(self, count, date: str):
        data = self.__api.scanners(
            scanner_type=sc.ScannerType.VolumeRank,
            count=count,
            date=date,
        )
        result = basic_pb2.StockVolumeRankList()
        for item in data:
            result.list.append(
                basic_pb2.StockVolumeRank(
                    code=item.code,
                    volume=item.total_volume,
                )
            )
        return result
