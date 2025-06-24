import logging
import threading
from queue import Queue, ShutDown
from typing import List

import shioaji as sj
import shioaji.constant as sc
from panther.basic import future_pb2, option_pb2, stock_pb2
from panther.stream import stream_pb2
from shioaji.contracts import Contract, Future, Option, Stock
from shioaji.order import Trade

from config.auth import ShioajiAuth
from logger import logger

logging.getLogger("shioaji").propagate = False


class Agent:
    max_subscribe_count = 200
    current_subscribe_count = 0

    def __init__(self):
        self.__api = sj.Shioaji()
        self.__login_progess = int()
        self.__login_status_lock = threading.Lock()

        # callback initialization avoid NoneType lint error
        self.non_block_order_callback = None

        # order map with lock
        # key is order_id
        self.__order_map: dict[str, Trade] = {}
        self.__order_map_lock = threading.Lock()

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

        # event callback
        self.__event_queue: Queue = Queue()

    def event_callback(self, resp_code: int, event_code: int, info: str, event: str):
        self.__event_queue.put(
            stream_pb2.ShioajiEvent(
                resp_code=resp_code,
                event_code=event_code,
                info=info,
                event=event,
            )
        )
        logger.warning("Resp code: %d, Event code: %d, Info: %s, Event: %s", resp_code, event_code, info, event)

    def update_local_order(self):
        with self.__order_map_lock:
            cache = self.__order_map.copy()
            self.__order_map = {}
            try:
                self.__api.update_status()
                for order in self.__api.list_trades():
                    self.__order_map[order.order.id] = order
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

    def login(self, auth: ShioajiAuth, is_main: bool):
        logger.info("Shioaji version: %s", self.get_sj_version())
        self.__api.quote.set_event_callback(self.event_callback)
        self.__api.quote.set_on_tick_fop_v1_callback(self.future_tick_callback)
        self.__api.quote.set_on_bidask_fop_v1_callback(self.future_bid_ask_callback)
        self.__api.login(
            api_key=auth.api_key,
            secret_key=auth.api_key_secret,
            contracts_cb=self.login_cb,
            subscribe_trade=is_main,
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
        if is_main is True:
            if self.__api.stock_account.signed is False or self.__api.futopt_account.signed is False:
                raise RuntimeError("account not sign")
            self.__api.set_order_callback(self.order_callback)
            self.update_local_order()

        return self

    def logout(self):
        try:
            self.__event_queue.shutdown()
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
                return -1
            if self.current_subscribe_count >= self.max_subscribe_count:
                return -1
            try:
                contract = self.get_future_contract_by_code(code)
                if contract is None:
                    logger.error("contract %s not found", code)
                    return code
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
                return None
            except Exception:
                return code

    def subscribe_future_bidask(self, code):
        with self.sub_lock:
            if code in self.bidask_sub_dict:
                return -1
            if self.current_subscribe_count >= self.max_subscribe_count:
                return -1
            try:
                contract = self.get_future_contract_by_code(code)
                if contract is None:
                    logger.error("contract %s not found", code)
                    return code
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
                return None
            except Exception:
                return code

    # def unsubscribe_future_tick(self, code):
    #     with self.sub_lock:
    #         if code in self.tick_sub_dict:
    #             try:
    #                 self.__api.quote.unsubscribe(
    #                     self.tick_sub_dict[code],
    #                     quote_type=sc.QuoteType.Tick,
    #                     version=sc.QuoteVersion.v1,
    #                 )
    #                 del self.tick_sub_dict[code]
    #                 logger.info(
    #                     "unsubscribe future tick %s %s",
    #                     code,
    #                     self.get_future_contract_by_code(code).name,
    #                 )
    #                 return None
    #             except Exception:
    #                 return code
    #         else:
    #             return -1

    def future_tick_callback(self, _, tick: sj.TickFOPv1):
        try:
            self.__tick_queue_map[tick.code].put(tick)
        except ShutDown:
            pass

    def future_bid_ask_callback(self, _, bidask: sj.BidAskFOPv1):
        try:
            self.__bidask_queue_map[bidask.code].put(bidask)
        except ShutDown:
            pass

    def get_event_queue(self):
        return self.__event_queue

    def get_tick_queue(self, code: str):
        with self.sub_lock:
            return self.__tick_queue_map.get(code, None)

    def get_bidask_queue(self, code: str):
        with self.sub_lock:
            return self.__bidask_queue_map.get(code, None)
