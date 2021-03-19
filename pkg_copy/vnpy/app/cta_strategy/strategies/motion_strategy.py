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

from vnpy.trader.constant import Interval, Status

from vnpy.app.cta_strategy.base import StopOrderStatus


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
    inside_bar_pos_num = 3
    points_diff = 2
    error_space = 2
    stop_lose_value = 10000
    open_amount = 5
    open_amount_style = "customized" ## costomized\fixed
    # k0_frequecy = "1m"  ## 1m\1h\1d 直接取回测设置中的周期即可，根据周期判断能否进行回测，并设置k0为相应的数值。



    parameters = [
        "inside_bar_unit",
        "inside_bar_length",
        "body_ratio",
        "k2_min_range",
        "k1_min_range",
        "inside_bar_pos_num",
        "points_diff",
        "error_space",
        "stop_lose_value",
        "open_amount",
        "open_amount_style"
    ]
    variables = [
        "atr_value"
    ]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

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
        # 0a, 0b, 1a, 1b
        self.target_position = {(str(i) + j):self.open_amount for i in range(self.inside_bar_pos_num) for j in ("a", "b")}
        # 每次更新trade和order时，要逐个属性考虑一下是否需要更新或者重置。
        self.pos_holdings = {
            i: {
                "direc": DIREC_LONG,
                "ph":PositionHolding(contract=c),
                "cost_basis": 0,
                "status": CLOSE_FINISHED,
                "stop_lose_price": 0,
                "stop_win_price": 0,
                "open_order": None,
                "stop_lose_order":None,
                "stop_win_order": None
            } for i in self.target_position.keys()
        }
        self.engine_params = {
            "size": self.cta_engine.size
        }

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化：" + self.__class__.__name__)

        self.k0 = {"ask1": 0, "bid1": 0}
        self.k1 = {"open": 0, "high": 0, "low": 0, "close": 0}
        self.k2 = {"open": 0, "high": 0, "low": 0, "close": 0}
        self.open_position_condition = False
        self.stop_lose_abs_distance = 0
        ## assert open_amount_style and inside_bar_unit
        self.open_amount_costomized = self.open_amount_style == "customized"

        # TODO：初始化持仓。

        #注册或者说配置一个参数，告知回测引擎从第几个bar之后开始跑正式回测。10天的数据都跨过去。这个函数会给callback赋值，所以请使用。
        #但是需要注意的是，在on_bar中，要含有以下逻辑，没有到10天，不可以下单。也就是self.inited = True之后才可以下单
        self.load_bar(10)


    def on_start(self):
        """
        Callback when strategy is started.
        """

        print(self.get_parameters())
        print(self.cta_engine.size)
        print(self.cta_engine.vt_symbol)
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
        # self.bgw.update_tick(tick)

    def on_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        # am = self.am
        # am.update_bar(bar)
        # load_bar 以及 inited，只是为了准备am数据
        self.k0["ask1"] = bar.close_price # ask1 卖一
        self.k0["bid1"] = bar.close_price # bid1 买一
        self.bgw.update_bar(bar) # trigger on_window_bar()

        if not self.inited:
            return
        # print("=======on_bar=======")
        # self.write_log("bar: " + str(bar.datetime))
        # print("ph ph active_orders: ", self.pos_holdings["0a"]["ph"].active_orders)
        # print("active_limit_orders: ", self.cta_engine.active_limit_orders)

        assert len(self.pos_holdings["0a"]["ph"].active_orders) ==len(self.cta_engine.active_limit_orders)
        assert self.pos == self.pos_holdings["0a"]["ph"].long_pos - self.pos_holdings["0a"]["ph"].short_pos

        # 下单逻辑，日后需要抽象出来，on_tick也需要调用。首先需要下达限价单，后续此处需要进行根据持仓情况下达止损单。
        if self.pos_holdings["0a"]["status"] in (CLOSE_FINISHED, OPEN_STARTED):
            open_order = self.pos_holdings["0a"].get("open_order")
            if self.open_position_condition and open_order is None: # 可以根据下单时间，计算open_order的持续时间，进行撤单、并设为None，实现多少个bar撤单
                if self.k0["ask1"] > self.k1["high"]:
                    # target_position 始终为正，根据开仓方向，计算order_amount的时候要进行符号方向的区别
                    self.write_log(self.get_signal_str(bar.datetime))
                    pos_amount = self.pos_holdings["0a"]["ph"].long_pos - self.pos_holdings["0a"]["ph"].short_pos
                    order_amount = round(self.target_position["0a"] - pos_amount)
                    vt_orderid = self.buy(self.k0["ask1"], order_amount)[0]
                    self.pos_holdings["0a"]["open_order"] = self.cta_engine.active_limit_orders[vt_orderid]
                    self.pos_holdings["0a"]["stop_lose_price"] = self.k1["low"] - self.error_space - self.points_diff
                    self.pos_holdings["0a"]["stop_win_price"] = self.k0["ask1"] + self.stop_lose_abs_distance
                    self.pos_holdings["0a"]["status"] = OPEN_STARTED
                    self.pos_holdings["0a"]["direc"] = DIREC_LONG
                elif self.k0["bid1"] < self.k1["low"]:
                    self.write_log(self.get_signal_str(bar.datetime))
                    pos_amount = self.pos_holdings["0a"]["ph"].long_pos - self.pos_holdings["0a"]["ph"].short_pos
                    order_amount = round(self.target_position["0a"] + pos_amount)
                    vt_orderid = self.short(self.k0["bid1"], order_amount)[0]
                    self.pos_holdings["0a"]["open_order"] = self.cta_engine.active_limit_orders[vt_orderid]
                    self.pos_holdings["0a"]["stop_lose_price"] = self.k1["high"] + self.error_space + self.points_diff
                    self.pos_holdings["0a"]["stop_win_price"] = self.k0["bid1"] - self.stop_lose_abs_distance
                    self.pos_holdings["0a"]["status"] = OPEN_STARTED
                    self.pos_holdings["0a"]["direc"] = DIREC_SHORT

        elif self.pos_holdings["0a"]["status"] in (OPEN_FINISHED, CLOSE_STARTED):
            stop_win_order = self.pos_holdings["0a"].get("stop_win_order")
            stop_lose_order = self.pos_holdings["0a"].get("stop_lose_order")
            stop_win_price = self.pos_holdings["0a"].get("stop_win_price")
            stop_lose_price = self.pos_holdings["0a"].get("stop_lose_price")
            if stop_win_order is None and stop_win_price != 0:
                if self.pos_holdings["0a"]["direc"] == DIREC_LONG:
                    vt_orderid = self.sell(stop_win_price, self.target_position["0a"])[0]
                else:
                    vt_orderid = self.cover(stop_win_price, self.target_position["0a"])[0]
                self.pos_holdings["0a"]["stop_win_order"] = self.cta_engine.active_limit_orders[vt_orderid]
                self.pos_holdings["0a"]["status"] = CLOSE_STARTED
            if stop_lose_order is None and stop_lose_price != 0:
                if self.pos_holdings["0a"]["direc"] == DIREC_LONG:
                    vt_orderid = self.sell(stop_lose_price, self.target_position["0a"], True)[0]
                else:
                    vt_orderid = self.cover(stop_lose_price, self.target_position["0a"], True)[0]
                self.pos_holdings["0a"]["stop_lose_order"] = self.cta_engine.active_stop_orders[vt_orderid]
                self.pos_holdings["0a"]["status"] = CLOSE_STARTED

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

        self.stop_lose_abs_distance = self.k1["high"] - self.k1["low"] + self.points_diff + self.error_space


        if self.k2["high"] >= self.k1["high"] and self.k2["low"] <= self.k1["low"]:
            self.inside_bar_signal = True
        else:
            self.inside_bar_signal = False

        condition_body = abs(self.k2["open"] - self.k2["close"]) >= self.body_ratio / 100 * abs(self.k2["high"] - self.k2["low"])  # 0 >= 0
        condition_k1_range = self.k1["high"] - self.k1["low"] > self.k1_min_range
        condition_k2_range = self.k2["high"] - self.k2["low"] > self.k2_min_range
        if self.inside_bar_signal and condition_body and condition_k1_range and condition_k2_range:
            if self.open_amount_costomized:
                self.target_position["0a"] = max(round(self.stop_lose_value / (self.stop_lose_abs_distance * self.engine_params["size"])), 2)
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
        self.write_log("="*10 + "on_order" + "="*10)
        self.write_log(self.get_order_str(order))

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
        # TODO: update_trade的时候计算cost_basis

        print("pos:" + str(self.pos))
        print("ph: pos", self.pos_holdings["0a"]["ph"].long_pos - self.pos_holdings["0a"]["ph"].short_pos)
        print("active_limit_order:", len(self.cta_engine.active_limit_orders))
        print("active_stop_order:", len(self.cta_engine.active_stop_orders))
        assert self.pos == self.pos_holdings["0a"]["ph"].long_pos - self.pos_holdings["0a"]["ph"].short_pos

        self.write_log("="*10 + "on_trade" + "="*10)
        self.write_log("pos: " + str(self.pos))

        if self.target_position["0a"] != 0 and (
                (self.pos_holdings["0a"]["ph"].long_pos - self.pos_holdings["0a"]["ph"].short_pos == self.target_position["0a"] and self.pos_holdings["0a"]["direc"] == DIREC_LONG) or
                (self.pos_holdings["0a"]["ph"].long_pos - self.pos_holdings["0a"]["ph"].short_pos == - self.target_position["0a"] and self.pos_holdings["0a"]["direc"] == DIREC_SHORT)) :
            self.pos_holdings["0a"]["status"] = OPEN_FINISHED
            self.pos_holdings["0a"]["open_order"] = None
        elif self.pos_holdings["0a"]["ph"].long_pos == 0 and self.pos_holdings["0a"]["ph"].short_pos ==0:
            self.pos_holdings["0a"]["status"] = CLOSE_FINISHED
            stop_win_order = self.pos_holdings["0a"]["stop_win_order"]
            stop_lose_order = self.pos_holdings["0a"]["stop_lose_order"]
            if stop_win_order:
                if stop_win_order.status != Status.ALLTRADED:
                    self.cancel_order(stop_win_order.vt_orderid)
                self.pos_holdings["0a"]["stop_win_order"] = None
                self.pos_holdings["0a"]["stop_win_price"] = 0
            if stop_lose_order:
                if stop_lose_order.status != StopOrderStatus.TRIGGERED:
                    self.cancel_order(stop_lose_order.stop_orderid)
                self.pos_holdings["0a"]["stop_lose_order"] = None
                self.pos_holdings["0a"]["stop_lose_price"] = 0

        # 建完仓，应该把open_order设置为None；
        # 平完仓，应该把两个stop_order设置为None，并将另一个stoporder、cancel掉

        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        print("======on_stop_order======")
        self.write_log("="*10 + "on_stop_order" + "="*10)
        self.write_log(self.get_stop_order_str(stop_order))

    def get_signal_str(self, dt):
        signal_str = "Signal Info\n%s\nk2O:%s, k2C:%s\nk2H:%s, k2L:%s\nK1H:%s, k1L:%s\nk0A:%s, k0B:%s" % (
            dt,
            self.k2["open"],
            self.k2["close"],
            self.k2["high"],
            self.k2["low"],
            self.k1["high"],
            self.k1["low"],
            self.k0["ask1"],
            self.k0["bid1"]
        )
        return signal_str

    def get_stop_order_str(self, order: StopOrder):
        order_str = "on_stop_order\n%s, %s\n%s, %s\n%s, %s" %(
            order.stop_orderid,
            order.status.name,
            order.direction.name,
            order.offset.name,
            order.volume,
            order.price
        )
        return order_str

    def get_order_str(self, order: OrderData):
        order_str = "on_order\n%s, %s\n%s, %s\n%s, %s" %(
            order.vt_orderid,
            order.status.name,
            order.direction.name,
            order.offset.name,
            order.traded,
            order.price
        )
        return order_str
