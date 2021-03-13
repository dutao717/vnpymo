from vnpy.app.cta_strategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)

OPEN_STARTED = 0
OPEN_FINISHED = 1
CLOSE_STARTED = 2
CLOSE_FINISHED = 3

DIREC_LONG = 0
DIREC_SHORT = 1

from vnpy.trader.object import ContractData

from vnpy.trader.converter import PositionHolding

from vnpy.trader.constant import Interval


class MotionStrategy(CtaTemplate):
    """"""

    author = "用Python的交易员"

    atr_value = 0

    ##  孕线策略
    inside_bar_unit = "minute"  ## 1m\1h\1d
    inside_bar_length = 5
    body_ratio = 50
    k2_min_range = 0
    k1_min_range = 0
    # k0_frequecy = "1m"  ## 1m\1h\1d 直接取回测设置中的周期即可，根据周期判断能否进行回测，并设置k0为相应的数值。



    parameters = [
        "inside_bar_unit",
        "inside_bar_length",
        "body_ratio",
        "k2_min_range",
        "k1_min_range"
    ]
    variables = [
        "atr_value"
    ]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        # self.bg = BarGenerator(self.on_bar)

        self.interval = {"minute": Interval.MINUTE}.get(self.inside_bar_unit)
        self.bgw = BarGenerator(self.on_bar, self.inside_bar_length, self.on_window_bar, self.interval)
        self.am = ArrayManager(100)  # 取决于历史数据准备多长 x * inside_bar_length，参考进阶开仓条件

        c = ContractData(
            gateway_name='',
            symbol=self.cta_engine.symbol,
            exchange=self.cta_engine.exchange,
            name=None,
            product=None,
            size=None,
            pricetick=None
        )
        print(self.cta_engine.vt_symbol, self.cta_engine.exchange)
        self.pos_holdings = {
            "0a": {
                "direc": DIREC_LONG,
                "ph":PositionHolding(contract=c),
                "cost_basis": 0,
                "status": CLOSE_FINISHED,
                "stop_lose_price": 0,
                "stop_win_price": 0,
                "open_order": None,
                "stop_lose_order":None,
                "stop_win_order": None
            },
        }

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化：" + self.__class__.__name__)
        self.inside_bars = {"k0": 0, "k1": 0, "k2": 0}

        self.k0 = {"ask1": 0, "bid1": 0}
        self.k1 = {"open": 0, "high": 0, "low": 0, "close": 0}
        self.k2 = {"open": 0, "high": 0, "low": 0, "close": 0}
        self.open_position_condition = False
        self.target_position = {"0a":0, "0b":0, "1a":0, "1b":0, "2a":0, "2b":0}

        self.load_bar(10)

    def on_start(self):
        """
        Callback when strategy is started.
        """
        self.write_log("策略启动")

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        # 等需要上市盘的时候，此处需要将on_bar的下单逻辑抽象一下，在此处也要进行调用。
        # self.bg.update_tick(tick)

    def on_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        # am = self.am
        # am.update_bar(bar)
        # if not am.inited:
        #     return
        print("=======on_bar=======")
        print("ph: active_orders", self.pos_holdings["0a"]["ph"].active_orders)
        updated_active_limit_orders = {k: v for (k, v) in self.cta_engine.active_limit_orders.items() if v.is_active()}
        print("updated_active_limit_orders:", updated_active_limit_orders)
        assert len(self.pos_holdings["0a"]["ph"].active_orders) ==len(self.cta_engine.active_limit_orders)

        self.k0["ask1"] = bar.close_price # ask1 卖一
        self.k0["bid1"] = bar.close_price # bid1 买一
        # self.write_log("bar: " + str(bar.datetime))
        # self.write_log("k0_last: " + str(self.k0_last))
        self.bgw.update_bar(bar) # trigger on_window_bar()

        ## 下单逻辑，日后需要抽象出来，on_tick也需要调用。首先需要下达限价单，后续此处需要进行根据持仓情况下达止损单。因此全局应该有一个目标仓位的仓位管理设置。
        # self.cancel_all()


        if self.pos_holdings["0a"]["status"] in (CLOSE_FINISHED, OPEN_STARTED):
            if self.open_position_condition:
                if self.k0["ask1"] > self.k1["high"]:
                    order_amount = round(self.target_position["0a"]) # - self.pos-short+long - self.pos—openorder)
                    if order_amount > 0:
                        self.buy(bar.close_price, self.target_position["0a"])
        elif self.pos_holdings["0a"]["status"] in (OPEN_FINISHED, CLOSE_STARTED):
            self.sell(self.k0["bid1"] + 10, self.target_position["0a"])
            self.sell(self.k0["bid1"] - 10, self.target_position["0a"], True)

        self.put_event()


    def on_window_bar(self, bar: BarData):

        self.k2["open"] = self.k1["open"]
        self.k2["high"] = self.k1["high"]
        self.k2["low"] = self.k1["low"]
        self.k2["close"] = self.k1["close"]
        self.k1["open"] = bar.open_price
        self.k1["high"] = bar.high_price
        self.k1["low"] = bar.low_price
        self.k1["close"] = bar.close_price


        if self.k2["high"] >= self.k1["high"] and self.k2["low"] <= self.k1["low"]:
            self.inside_bar_signal = True
        else:
            self.inside_bar_signal = False

        condition_body = abs(self.k2["open"] - self.k2["close"]) >= self.body_ratio / 100 * abs(self.k2["high"] - self.k2["low"])  # 0 >= 0
        condition_k1_range = self.k1["high"] - self.k1["low"] > self.k1_min_range
        condition_k2_range = self.k2["high"] - self.k2["low"] > self.k2_min_range
        if self.inside_bar_signal and condition_body and condition_k1_range and condition_k2_range:
            self.write_log("w_bar: " + str(bar.datetime))
            self.write_log("k1_high: " + str(self.k1["high"]))
            self.write_log("k1_low: " + str(self.k1["low"]))
            self.write_log("k2_high: " + str(self.k2["high"]))
            self.write_log("k2_low: " + str(self.k2["low"]))
            self.write_log("k2_open: " + str(self.k2["open"]))
            self.write_log("k2_close: " + str(self.k2["close"]))
            self.write_log("buy or short OK.")
            self.target_position["0a"] = 5
            self.open_position_condition = True
        else:
            self.open_position_condition = False

        self.put_event()
        pass

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        buy函数运行的时候，已经将order添加到active_limit_orders,但不会触发on_order,只有撮合的时候，会对order进行状态更新。
        所以active_list_orders即便是只选择alive的order，也不会和ph.active_orders相等。
        ph更新之后active_orders只会有not_traded和part_traded。active_list_orders中值有not_traded和part_traded的数量等于ph.active_orders
        """
        print("======on_order======")
        print("order: ", order)
        print("bar: " + str(order.datetime))

        self.pos_holdings["0a"]["ph"].update_order(order)
        self.write_log("on_order: buy 1000")

        print("pos:" + str(self.pos))
        print("active_limit_order:" ,self.cta_engine.active_limit_orders)
        print("active_stop_order:", self.cta_engine.active_stop_orders)
        print("ph: active_orders", self.pos_holdings["0a"]["ph"].active_orders)

        updated_active_limit_orders = {k: v for (k, v) in self.cta_engine.active_limit_orders.items() if v.is_active()}
        print("updated_active_limit_orders:", updated_active_limit_orders)






    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        on_trade里面不要下单，只更新状态，因为如果下单，也是等下一个bar再成交，但是却破坏了当前bar的原子性。使得当前bar一开始的时候，ph.active_bars和active_limit_orders不相等
        """
        print("=========on_trade=======")
        print("trade:", trade)
        # 此处需要增加根据成交回报下达止损单的逻辑，但目前还不涉及实盘，不着急。
        self.pos_holdings["0a"]["ph"].update_trade(trade)

        print("pos:" + str(self.pos))
        print("ph: pos", self.pos_holdings["0a"]["ph"].long_pos + self.pos_holdings["0a"]["ph"].short_pos)
        print("active_limit_order:", len(self.cta_engine.active_limit_orders))
        print("active_stop_order:", len(self.cta_engine.active_stop_orders))
        assert self.pos == self.pos_holdings["0a"]["ph"].long_pos + self.pos_holdings["0a"]["ph"].short_pos


        self.write_log("pos: " + str(self.pos))
        if self.pos_holdings["0a"]["ph"].long_pos + self.pos_holdings["0a"]["ph"].short_pos == self.target_position["0a"] and self.target_position != 0:
            self.pos_holdings["0a"]["status"] = OPEN_FINISHED
        elif self.pos_holdings["0a"]["ph"].long_pos == 0 and self.pos_holdings["0a"]["ph"].short_pos ==0:
            self.pos_holdings["0a"]["status"] = CLOSE_FINISHED

        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass
