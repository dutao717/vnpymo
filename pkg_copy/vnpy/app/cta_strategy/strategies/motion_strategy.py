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

from vnpy.trader.object import ContractData, OrderData
from vnpy.trader.converter import PositionHolding
from vnpy.trader.constant import Interval, Status, Direction
from vnpy.app.cta_strategy.base import StopOrderStatus, StopOrder


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
    inside_bar_pos_num = 1
    points_diff = 2
    error_space = 2
    stop_loss_value = 10000
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
        "stop_loss_value",
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
        print(self.cta_engine.vt_symbol, self.cta_engine.exchange)
        self.pos_man = PosManager(
            symbol=self.cta_engine.symbol,
            exchange=self.cta_engine.exchange,
            tgt_amt=self.open_amount,
            names=[(str(i) + j) for i in range(self.inside_bar_pos_num) for j in ("a", "b")]
        )
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
        self.stop_loss_abs_distance = 0
        self.open_amount_costomized = self.open_amount_style == "customized"
        # TODO：初始化持仓。
        # 注册或者说配置一个参数，告知回测引擎从第几个bar之后开始跑正式回测。10天的数据都跨过去。这个函数会给callback赋值，所以请使用。
        # 但是需要注意的是，在on_bar中，要含有以下逻辑，没有到10天，不可以下单。也就是self.inited = True之后才可以下单
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

        assert len(self.pos_man.get_active_orders()) ==len(self.cta_engine.active_limit_orders)
        assert self.pos == self.pos_man.get_pos_amt()

        # 下单逻辑，日后需要抽象出来，on_tick也需要调用。首先需要下达限价单，后续此处需要进行根据持仓情况下达止损单。
        # ab单同时处于close_finished和open_started才能开仓。对单号1、2、3进行循环。内层对ab进行循环。
        pm = self.pos_man
        p_name = "0a"

        if pm.get_status(p_name) in (CLOSE_FINISHED, OPEN_STARTED):
            open_order = pm.get_open_order(p_name)
            if self.open_position_condition and open_order is None: # 可以根据下单时间，计算open_order的持续时间，进行撤单、并设为None，实现多少个bar撤单
                if self.k0["ask1"] > self.k1["high"]:
                    if self.open_amount_costomized:
                        tgt_amt = max(
                            round(self.stop_loss_value / (self.stop_loss_abs_distance * self.engine_params["size"])), 2)
                        pm.set_tgt_amt(p_name, tgt_amt)
                    # target_position 始终为正，根据开仓方向，计算order_amount的时候要进行符号方向的区别
                    self.write_log(self.get_signal_str(bar.datetime))
                    order_amount = round(pm.get_tgt_amt(p_name) - pm.get_pos_amt(p_name))
                    vt_orderid = self.buy(self.k0["ask1"], order_amount)[0]
                    open_order = self.cta_engine.active_limit_orders[vt_orderid]
                    pm.set_open_order(p_name, open_order)
                    pm.set_stop_prices(
                        name=p_name,
                        stop_loss_price=self.k1["low"] - self.error_space - self.points_diff,
                        stop_profit_price=self.k0["ask1"] + self.stop_loss_abs_distance
                    )
                elif self.k0["bid1"] < self.k1["low"]:
                    if self.open_amount_costomized:
                        tgt_amt = max(
                            round(self.stop_loss_value / (self.stop_loss_abs_distance * self.engine_params["size"])), 2)
                        pm.set_tgt_amt(p_name, tgt_amt)
                    self.write_log(self.get_signal_str(bar.datetime))
                    order_amount = round(pm.get_tgt_amt(p_name) + pm.get_pos_amt(p_name))
                    vt_orderid = self.short(self.k0["bid1"], order_amount)[0]
                    open_order = self.cta_engine.active_limit_orders[vt_orderid]
                    pm.set_open_order(p_name, open_order)
                    pm.set_stop_prices(
                        name=p_name,
                        stop_loss_price=self.k1["high"] + self.error_space + self.points_diff,
                        stop_profit_price=self.k0["bid1"] - self.stop_loss_abs_distance
                    )
        # ab单可以单独进行平仓的设定。直接对1a\1b\2a\2b\3a\3b进行循环。
        elif pm.get_status(p_name) in (OPEN_FINISHED, CLOSE_STARTED):
            stop_profit_order = pm.get_stop_profit_order(p_name)
            stop_loss_order = pm.get_stop_loss_order(p_name)
            stop_loss_price, stop_profit_price = pm.get_stop_prices(p_name)
            direc = pm.get_direc(p_name)
            if stop_profit_order is None and stop_profit_price != 0:
                if direc == Direction.LONG:
                    vt_orderid = self.sell(stop_profit_price, pm.get_tgt_amt(p_name))[0]
                else:
                    vt_orderid = self.cover(stop_profit_price, pm.get_tgt_amt(p_name))[0]
                pm.set_stop_profit_order(p_name, self.cta_engine.active_limit_orders[vt_orderid])
            if stop_loss_order is None and stop_loss_price != 0:
                if direc == Direction.LONG:
                    vt_orderid = self.sell(stop_loss_price, pm.get_tgt_amt(p_name), True)[0]
                else:
                    vt_orderid = self.cover(stop_loss_price, pm.get_tgt_amt(p_name), True)[0]
                pm.set_stop_loss_order(p_name, self.cta_engine.active_stop_orders[vt_orderid])

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

        self.stop_loss_abs_distance = self.k1["high"] - self.k1["low"] + self.points_diff + self.error_space


        if self.k2["high"] >= self.k1["high"] and self.k2["low"] <= self.k1["low"]:
            self.inside_bar_signal = True
        else:
            self.inside_bar_signal = False

        condition_body = abs(self.k2["open"] - self.k2["close"]) >= self.body_ratio / 100 * abs(self.k2["high"] - self.k2["low"])  # 0 >= 0
        condition_k1_range = self.k1["high"] - self.k1["low"] > self.k1_min_range
        condition_k2_range = self.k2["high"] - self.k2["low"] > self.k2_min_range
        if self.inside_bar_signal and condition_body and condition_k1_range and condition_k2_range:

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

        # 在此处应该添加逻辑，判断当前是否有triggered的stoporder，如果有的话，检查symbol\direction\offset\volume是否相同，如果相同，则替换掉。
        # 根据订单编号进行update
        pm = self.pos_man
        p_name = "0a"
        stop_loss_order = pm.get_stop_loss_order(p_name)
        print(stop_loss_order)
        print(order)
        if (
                stop_loss_order is not None and stop_loss_order.status == StopOrderStatus.TRIGGERED and
                order.vt_symbol == stop_loss_order.vt_symbol and
                order.direction == stop_loss_order.direction and order.price == stop_loss_order.price and
                order.offset == stop_loss_order.offset and order.volume == stop_loss_order.volume):
            print("set_stop_loss_order")
            print(stop_loss_order)
            print(order)

            pm.set_stop_loss_order(p_name, order)
        pm.update_order(order)
        self.write_log("="*10 + "on_order" + "="*10)
        self.write_log(self.get_order_str(order))

        print("pos:" + str(self.pos))
        print("active_limit_order:" ,self.cta_engine.active_limit_orders)
        print("active_stop_order:", self.cta_engine.active_stop_orders)
        print("ph: active_orders", pm.get_active_orders(p_name))

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
        # 根据订单变化进行update
        pm = self.pos_man
        pm.update_trade(trade)
        # TODO: update_trade的时候计算cost_basis

        p_name = pm.pos_name_of_trade(trade)

        print("pos:" + str(self.pos))
        print("ph: pos", pm.get_pos_amt())
        print("active_limit_order:", len(self.cta_engine.active_limit_orders))
        print("active_stop_order:", len(self.cta_engine.active_stop_orders))
        assert self.pos == pm.get_pos_amt()

        self.write_log("="*10 + "on_trade" + "="*10)
        self.write_log("pos: " + str(self.pos))

        # ab单可以单独进行平仓的设定。直接对1a\1b\2a\2b\3a\3b进行循环。
        tgt_amt = pm.get_tgt_amt(p_name)
        pos_amt = pm.get_pos_amt(p_name)
        pos_l_amt = pm.get_pos_amt(p_name, Direction.LONG)
        pos_s_amt = pm.get_pos_amt(p_name, Direction.SHORT)
        direc = pm.get_direc(p_name)
        if tgt_amt != 0 and ((pos_amt == tgt_amt and direc == Direction.LONG) or (pos_amt == - tgt_amt and direc == Direction.SHORT)):
            pm.set_open_order(p_name, None)
        elif pos_l_amt == 0 and pos_s_amt == 0:
            pm.set_status(p_name, CLOSE_FINISHED)
            stop_profit_order = pm.get_stop_profit_order(p_name)
            stop_loss_order = pm.get_stop_loss_order(p_name)
            if stop_profit_order:
                if stop_profit_order.status != Status.ALLTRADED:
                    self.cancel_order(stop_profit_order.vt_orderid)
                pm.set_stop_profit_order(p_name, None)
            if stop_loss_order:
                if type(stop_loss_order) == StopOrder:
                    if stop_loss_order.status != StopOrderStatus.TRIGGERED:
                        self.cancel_order(stop_loss_order.stop_orderid)
                else:
                    if stop_loss_order.status != Status.ALLTRADED:
                        self.cancel_order(stop_loss_order.vt_orderid)
                pm.set_stop_loss_order(p_name, None)

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


class PosManager:
    def __init__(self, symbol, exchange, tgt_amt, names=None):
        """
        :param symbol: str, contract symbol
        :param exchange: str, contract exchange
        :param names: list of position names
        """
        c = ContractData(
            gateway_name='',
            symbol=symbol,
            exchange=exchange,
            name=None,
            product=None,
            size=None,
            pricetick=None
        )

        self.__pos_holdings = {i: PositionHolding(contract=c) for i in names}
        self.__pos_data = {
            i: {
                "tgt_amt": tgt_amt,
                "open_order": None,
                "direc": Direction.LONG,
                "status": CLOSE_FINISHED,
                "stop_loss_price": 0,
                "stop_profit_price": 0,
                "stop_loss_order":None,
                "stop_profit_order": None,
                "cost_basis": 0
            } for i in names
        }
        self.__order_pos_map = {}

    def get_pos_amt(self, name=None, direc=None):
        """
        :param name: pos name
        :return: position amount, if amount is greater than 0, the pos is net long, otherwise, net short
        """
        res = 0
        if name is None:
            for k in self.__pos_holdings.keys():
                ph = self.__pos_holdings[k]
                if direc is None:
                    res += ph.long_pos - ph.short_pos
                elif direc == Direction.LONG:
                    res += ph.long_pos
                elif direc == Direction.SHORT:
                    res += ph.short_pos
        else:
            ph = self.__pos_holdings[name]
            if direc is None:
                res = ph.long_pos - ph.short_pos
            elif direc == Direction.LONG:
                res = ph.long_pos
            elif direc == Direction.SHORT:
                res = ph.short_pos
        return res

    def get_tgt_amt(self, name):
        return self.__pos_data[name]["tgt_amt"]

    def set_tgt_amt(self, name, tgt_amt):
        self.__pos_data[name]["tgt_amt"] = tgt_amt

    def get_direc(self, name):
        return self.__pos_data[name]["direc"]

    def set_direc(self, name, direc):
        self.__pos_data[name]["direc"] = direc

    def get_status(self, name):
        return self.__pos_data[name]["status"]

    def set_status(self, name, status):
        self.__pos_data[name]["status"] = status

    def get_open_order(self, name):
        return self.__pos_data[name]["open_order"]

    def set_open_order(self, name, open_order):
        if open_order is None:
            open_order_old = self.__pos_data[name]["open_order"]
            self.__pos_data[name]["open_order"] = open_order
            self.__pos_data[name]["status"] = OPEN_FINISHED
            self.__order_pos_map.pop(open_order_old.vt_orderid)
        else:
            self.__pos_data[name]["open_order"] = open_order
            self.__pos_data[name]["direc"] = open_order.direction
            self.__pos_data[name]["status"] = OPEN_STARTED
            self.__order_pos_map[open_order.vt_orderid] = name

    def set_stop_prices(self, name, stop_loss_price, stop_profit_price):
        self.__pos_data[name]["stop_loss_price"] = stop_loss_price
        self.__pos_data[name]["stop_profit_price"] = stop_profit_price

    def get_stop_prices(self, name):
        pd = self.__pos_data[name]
        return [pd["stop_loss_price"], pd["stop_profit_price"]]

    def get_stop_loss_order(self, name):
        return self.__pos_data[name]["stop_loss_order"]

    def get_stop_profit_order(self, name):
        return self.__pos_data[name]["stop_profit_order"]

    def set_stop_loss_order(self, name, stop_loss_order):
        # 止损单转成限价单也用这个方法
        if stop_loss_order is None:
            stop_order_old = self.__pos_data[name]["stop_loss_order"]
            self.__pos_data[name]["stop_loss_order"] = stop_loss_order
            self.__pos_data[name]["stop_loss_price"] = 0
            # self.__pos_data[name]["status"] = CLOSE_FINISHED
            if type(stop_order_old) == OrderData:
                self.__order_pos_map.pop(stop_order_old.vt_orderid)
        else:
            self.__pos_data[name]["stop_loss_order"] = stop_loss_order
            self.__pos_data[name]["status"] = CLOSE_STARTED
            if type(stop_loss_order) == OrderData:
                self.__order_pos_map[stop_loss_order.vt_orderid] = name

    def set_stop_profit_order(self, name, stop_profit_order):
        if stop_profit_order is None:
            stop_order_old = self.__pos_data[name]["stop_profit_order"]
            self.__pos_data[name]["stop_profit_order"] = stop_profit_order
            self.__pos_data[name]["stop_profit_price"] = 0
            # self.__pos_data[name]["status"] = CLOSE_FINISHED
            if type(stop_order_old) == OrderData:
                self.__order_pos_map.pop(stop_order_old.vt_orderid)
        else:
            self.__pos_data[name]["stop_profit_order"] = stop_profit_order
            self.__pos_data[name]["status"] = CLOSE_STARTED
            self.__order_pos_map[stop_profit_order.vt_orderid] = name

    def update_order(self, order):
        # 可能会有order不存在的情况，只对现存的order进行更新
        # order.
        name = self.__order_pos_map.get(order.vt_orderid)
        if name is not None:
            self.__pos_holdings[name].update_order(order)

    def get_active_orders(self, name=None):
        if name is None:
            res = {}
            for i in self.__pos_holdings.values():
                res.update(i.active_orders)
            return res
        else:
            return self.__pos_holdings[name].active_orders

    def update_trade(self, trade):
        print(self.__order_pos_map)
        vt_orderid = ".".join([trade.gateway_name, trade.orderid])
        name = self.__order_pos_map[vt_orderid]  # 理论上一定会有对应的order的。所以，不用get
        ph = self.__pos_holdings[name]
        ph.update_trade(trade)

    def pos_name_of_trade(self, trade):
        vt_orderid = ".".join([trade.gateway_name, trade.orderid])
        name = self.__order_pos_map[vt_orderid]  # 理论上一定会有对应的order的。所以，不用get
        return name

