import pandas as pd

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

    ## 孕线策略
    # a_step_level.csv等配置文件所在的目录，设置为本地vnpymo项目的目录
    config_file_path = "D:\\workspace_py3\\work_vnpy\\vnpymo\\"
    # config_file_path = "F:\\4_workspace\\py3\\work_vnpy\\vnpymo\\"
    # 孕线周期的时间单位，可选值是minute\hour
    inside_bar_unit = "minute"  ## 1m\1h\1d
    # 孕线周期的时间长度，结合时间单位确定周期。
    inside_bar_length = 5
    # 实体比例（%）
    body_ratio = 50
    # K2 最小波幅（元）
    k2_min_range = 0
    # K1 最小波幅（元）
    k1_min_range = 0
    # 点差（元）
    points_diff = 10
    # 容错空间（元）
    error_space = 5
    # 固定开仓手数
    open_amount = 5
    # 开仓数量方式：customized/fixed，前者条件下，自定义止损金额才可用，后者条件下，固定开仓手数才可用。
    open_amount_style = "customized" ## costomized\fixed
    # b仓盈亏比达到F倍以后，每增加1个R，止损同步上升R的数量
    delta_loss_ratio = 1.0
    # b仓盈亏比达到F被以后，每增加1个R，止盈同步上升R的数量
    delta_profit_ratio = 2.0
    # 孕线信号最大持有数量，目前只支持3，其他数量下，程序会有意外问题。
    inside_bar_pos_num = 3
    # 自定义止损金额，格式：仓号^金额_仓号^金额_仓号^金额，数量和孕线信号最大持有数量相匹配
    stop_loss_values_str = "0^10000_1^15000_2^20000"

    parameters = [
        "config_file_path",
        "inside_bar_unit",
        "inside_bar_length",
        "body_ratio",
        "k2_min_range",
        "k1_min_range",
        "points_diff",
        "error_space",
        "open_amount",
        "open_amount_style",
        "delta_loss_ratio",
        "delta_profit_ratio",
        "inside_bar_pos_num",
        "stop_loss_values_str",
    ]
    variables = [
        "atr_value"
    ]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.interval = {"minute": Interval.MINUTE, "hour": Interval.HOUR}.get(self.inside_bar_unit)
        self.bgw = BarGenerator(self.on_bar, self.inside_bar_length, self.on_window_bar, self.interval)
        self.am = ArrayManager(100)  # 取决于历史数据准备多长 x * inside_bar_length，参考进阶开仓条件
        print(self.cta_engine.vt_symbol, self.cta_engine.exchange)
        a_stop_levels = pd.read_csv(self.config_file_path + "a_stop_levels.csv", index_col=0)
        b_stop_levels = pd.read_csv(self.config_file_path + "b_stop_levels.csv", index_col=0)
        stop_levels = {"a": a_stop_levels, "b": b_stop_levels, "b_top":{"delta_loss_ratio": self.delta_loss_ratio, "delta_profit_ratio": self.delta_profit_ratio}}

        self.pos_man = PosManager(
            symbol=self.cta_engine.symbol,
            exchange=self.cta_engine.exchange,
            tgt_amt=self.open_amount,
            stop_levels=stop_levels,
            names=[(str(i) + j) for i in range(self.inside_bar_pos_num) for j in ("a", "b")]
        )
        self.pos_man.set_enabled("0a", True)
        self.pos_man.set_enabled("0b", True)
        self.engine_params = {
            "size": self.cta_engine.size
        }
        self.stop_loss_values = dict([(i.split("^")[0], float(i.split("^")[1])) for i in self.stop_loss_values_str.split("_")])
        self.continuous_signal_operations = pd.read_csv(
            self.config_file_path + "continuous_signal_operations.csv",
            index_col=0).on_trade_op.to_dict()



    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.print_log("策略初始化：" + self.__class__.__name__)
        self.k0 = {"ask1": 0, "bid1": 0}
        self.k0_last = {"ask1": 0, "bid1": 0}
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
        print(self.cta_engine.pricetick)
        self.print_log("策略启动")

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.print_log("策略停止")

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
        self.k0_last["ask1"] = self.k0["ask1"]
        self.k0_last["bid1"] = self.k0["bid1"]
        self.k0["ask1"] = bar.close_price # ask1 卖一
        self.k0["bid1"] = bar.close_price # bid1 买一
        self.bgw.update_bar(bar) # trigger on_window_bar()

        if not self.inited:
            return

        assert len(self.pos_man.get_active_orders()) ==len(self.cta_engine.active_limit_orders)
        assert self.pos == self.pos_man.get_pos_amt()

        # 下单逻辑，日后需要抽象出来，on_tick也需要调用。首先需要下达限价单，后续此处需要进行根据持仓情况下达止损单。
        # ab单同时处于close_finished和open_started才能开仓。对单号1、2、3进行循环。内层对ab进行循环。
        pm = self.pos_man

        condition_long = self.k0["ask1"] > self.k1["high"]
        condition_short = self.k0["bid1"] < self.k1["low"]
        inside_bar_dts = self.pos_man.get_all_inside_bar_dts()
        for p_num in range(self.inside_bar_pos_num):
            p_a_name = str(p_num) + "a"
            p_b_name = str(p_num) + "b"
            if self.open_position_condition and self.inside_bar_dt not in inside_bar_dts and \
                    (condition_long or condition_short) and \
                    pm.is_enabled(p_a_name) and pm.is_enabled(p_b_name) and \
                    pm.get_status(p_a_name) in (CLOSE_FINISHED, OPEN_STARTED) and \
                    pm.get_status(p_b_name) in (CLOSE_FINISHED, OPEN_STARTED):
                # 对于3号仓开仓的特殊逻辑：只有1号仓盈利，才能开3号仓
                if p_num == 2 and (not pm.is_gaining_pnum(0, bar.close_price)):
                    self.print_log("====%s：仓号：%s 目前处于亏损状态，不能开仓====" % (self.cta_engine.datetime, p_num))
                    continue
                for p_name in [str(p_num) + j for j in ["a", "b"]]:
                    open_order = pm.get_open_order(p_name)
                    if open_order is None: # 可以根据下单时间，计算open_order的持续时间，进行撤单、并设为None，实现多少个bar撤单
                        self.print_log(self.get_signal_str(self.cta_engine.datetime))
                        if self.open_amount_costomized:
                            tgt_amt = max(
                                round(self.stop_loss_values[str(p_num)] / (
                                        self.stop_loss_abs_distance * self.engine_params["size"]) / 2), 1) # 每个仓是0.5的持仓量
                            pm.set_tgt_amt(p_name, tgt_amt)

                        if condition_long:
                            # target_position 始终为正，根据开仓方向，计算order_amount的时候要进行符号方向的区别
                            order_amount = round(pm.get_tgt_amt(p_name) - pm.get_pos_amt(p_name))
                            vt_orderid = self.buy(self.k0["ask1"], order_amount)[0]
                            stop_loss_price=self.k1["low"] - self.error_space - self.points_diff
                            # TODO: max a b stop_level 1
                            stop_profit_price=self.k0["ask1"] + self.stop_loss_abs_distance * 100
                        else:
                            order_amount = round(pm.get_tgt_amt(p_name) + pm.get_pos_amt(p_name))
                            vt_orderid = self.short(self.k0["bid1"], order_amount)[0]
                            stop_loss_price=self.k1["high"] + self.error_space + self.points_diff
                            # TODO: max a b stop_level 1
                            stop_profit_price=self.k0["bid1"] - self.stop_loss_abs_distance * 100

                        open_order = self.cta_engine.active_limit_orders[vt_orderid]
                        pm.set_open_order(p_name, open_order)
                        pm.set_inside_bar_dt(p_name, self.inside_bar_dt)
                        pm.set_stop_loss_abs_distance(p_name, self.stop_loss_abs_distance)
                        pm.set_init_stop_loss_price(p_name, stop_loss_price)
                        pm.set_stop_prices(
                            name=p_name,
                            stop_loss_price=stop_loss_price,
                            stop_profit_price=stop_profit_price
                        )
                        self.print_log(
                            "=====%s: 开仓下单=====\n仓名: %s\n孕线: %s\n方向: %s\n数量: %s\n"
                            "止盈价: %s\n止损价: %s\n止损绝对距离: %s\n" %(
                                self.cta_engine.datetime,
                                p_name,
                                self.inside_bar_dt,
                                "多" if condition_long else "空",
                                order_amount,
                                stop_profit_price,
                                stop_loss_price,
                                self.stop_loss_abs_distance
                            )
                        )
                        self.print_log(pm.get_pos_data_str(p_name, self.cta_engine.datetime))
        # ab单可以单独进行平仓的设定。直接对1a\1b\2a\2b\3a\3b进行循环。
        for p_name in pm.names:
            if pm.get_status(p_name) in (OPEN_FINISHED, CLOSE_STARTED):
                stop_profit_order = pm.get_stop_profit_order(p_name)
                stop_loss_order = pm.get_stop_loss_order(p_name)
                stop_loss_price, stop_profit_price = pm.get_stop_prices(p_name)
                direc = pm.get_direc(p_name)
                if stop_profit_order is None and stop_profit_price != 0:
                    if direc == Direction.LONG:
                        print(stop_profit_price, pm.get_tgt_amt(p_name))
                        vt_orderid = self.sell(stop_profit_price, pm.get_tgt_amt(p_name))[0]
                    else:
                        vt_orderid = self.cover(stop_profit_price, pm.get_tgt_amt(p_name))[0]
                    pm.set_stop_profit_order(p_name, self.cta_engine.active_limit_orders[vt_orderid])
                    self.print_log(
                        "=====%s: 止盈下单=====\n仓名: %s\n方向: %s\n数量: %s\n止盈价: %s\n" % (
                            self.cta_engine.datetime,
                            p_name,
                            direc,
                            pm.get_tgt_amt(p_name),
                            stop_profit_price
                        )
                    )
                if stop_loss_order is None and stop_loss_price != 0:
                    if direc == Direction.LONG:
                        vt_orderid = self.sell(stop_loss_price, pm.get_tgt_amt(p_name), True)[0]
                    else:
                        vt_orderid = self.cover(stop_loss_price, pm.get_tgt_amt(p_name), True)[0]
                    pm.set_stop_loss_order(p_name, self.cta_engine.active_stop_orders[vt_orderid])
                    self.print_log(
                        "=====%s: 止损下单=====\n仓名: %s\n方向: %s\n数量: %s\n止损价: %s\n" % (
                            self.cta_engine.datetime,
                            p_name,
                            direc,
                            pm.get_tgt_amt(p_name),
                            stop_loss_price
                        )
                    )
                if (stop_profit_order is not None) and (stop_loss_order is not None):
                    curr_price = self.k0["ask1"] if direc == Direction.LONG else self.k0["bid1"]
                    stop_level = pm.get_stop_level(p_name)
                    if pm.get_special_close(p_name):
                        # 强制平仓，将止盈单挂到市价
                        stop_profit_order = pm.get_stop_profit_order(p_name)
                        self.cancel_order(stop_profit_order.vt_orderid)
                        pm.set_stop_profit_order(p_name, None)
                        stop_profit_price_1 = curr_price - self.cta_engine.pricetick * (
                            1 if direc == Direction.LONG else -1) * 1
                        pm.set_stop_prices(p_name, stop_profit_price=stop_profit_price_1)
                        self.print_log(
                            "=====%s: 强制平仓挂止盈市价单=====\n仓名: %s\n方向: %s\n当前价格: %s\n挂单价格: %s\n" % (
                                self.cta_engine.datetime,
                                p_name,
                                direc,
                                curr_price,
                                stop_profit_price_1,
                            )
                        )

                    elif pm.adjust_stop_prices(p_name, curr_price):
                        # adjust_change_stop_level true, then set None and cancel and set new price

                        stop_profit_order = pm.get_stop_profit_order(p_name)
                        stop_loss_order = pm.get_stop_loss_order(p_name)

                        self.cancel_order(stop_profit_order.vt_orderid)
                        stop_loss_orderid = \
                            stop_loss_order.stop_orderid if type(stop_loss_order) == StopOrder else \
                                stop_loss_order.vt_orderid
                        self.cancel_order(stop_loss_orderid)
                        pm.set_stop_profit_order(p_name, None)
                        pm.set_stop_loss_order(p_name, None)
                        stop_loss_price_1, stop_profit_price_1 = pm.get_stop_prices(p_name)
                        self.print_log(
                            "=====%s: 止盈止损撤单重置=====\n仓名: %s\n方向: %s\n买入成本: %s\n当前价格: %s\n止损绝对距离: %s\n"
                            "原stop_level: %s, 新stop_level: %s\n原止损价: %s, 新止损价: %s\n原止盈价: %s, 新止盈价: %s\n" % (
                                self.cta_engine.datetime,
                                p_name,
                                direc,
                                pm.get_cost_basis(p_name),
                                curr_price,
                                pm.get_stop_loss_abs_distance(p_name),
                                stop_level,
                                pm.get_stop_level(p_name),
                                stop_loss_price,
                                stop_loss_price_1,
                                stop_profit_price,
                                stop_profit_price_1,
                            )
                        )

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
            self.inside_bar_dt = bar.datetime
        else:
            self.inside_bar_signal = False

        condition_body = \
            abs(self.k2["open"] - self.k2["close"]) >= \
            self.body_ratio / 100 * abs(self.k2["high"] - self.k2["low"])  # 0 >= 0
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
        ph更新之后active_orders只会有not_traded和part_traded。
        active_list_orders中值有not_traded和part_traded的数量等于ph.active_orders
        """

        # 在此处应该添加逻辑，判断当前是否有triggered的stoporder
        # 如果有的话，检查symbol\direction\offset\volume是否相同，如果相同，则替换掉。
        # 根据订单编号进行update
        pm = self.pos_man
        # 此处不能直接获取p_name,如果是stop_loss_order转成order的话。
        # 首先是看能不能获取，如果存在，则返回不存在，则应该把所有的triggered_order都拿出来，然后和当前的order进行对比。
        if pm.pos_name_of_order(order) is None:
            triggerred_stop_orders = {}
            stop_loss_order_set = False
            for p_name in pm.names:
                stop_loss_order = pm.get_stop_loss_order(p_name)
                if stop_loss_order is not None and type(stop_loss_order) == StopOrder and \
                        stop_loss_order.status == StopOrderStatus.TRIGGERED:
                    triggerred_stop_orders[p_name] = stop_loss_order
            for p_name, stop_loss_order in triggerred_stop_orders.items():
                if (
                        order.vt_symbol == stop_loss_order.vt_symbol and
                        order.direction == stop_loss_order.direction and order.price == stop_loss_order.price and
                        order.offset == stop_loss_order.offset and order.volume == stop_loss_order.volume):
                    stop_loss_order_set = True
                    pm.set_stop_loss_order(p_name, order)
                    self.print_log(
                        "=====%s: 止损单触发=====\n原止损单: %s\n新限价单: %s\n" %(
                            self.cta_engine.datetime,
                            stop_loss_order.stop_orderid,
                            order.vt_orderid
                        )
                    )
                    break
            assert stop_loss_order_set, "Order id can't be found, and no triggered stop order matched."
        pm.update_order(order)
        self.print_log(self.get_order_str(order, self.cta_engine.datetime))

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        on_trade里面不要下单，只更新状态，因为如果下单，也是等下一个bar再成交，但是却破坏了当前bar的原子性。
        使得当前bar一开始的时候，ph.active_bars和active_limit_orders不相等
        """
        # 此处需要增加根据成交回报下达止损单的逻辑，但目前还不涉及实盘，不着急。
        # 根据订单变化进行update

        pm = self.pos_man
        pm.update_trade(trade)
        p_name = pm.pos_name_of_trade(trade)
        assert self.pos == pm.get_pos_amt()

        self.print_log("=====%s: On Trade=====\n" % self.cta_engine.datetime)

        # ab单可以单独进行平仓的设定。直接对1a\1b\2a\2b\3a\3b进行循环。
        tgt_amt = pm.get_tgt_amt(p_name)
        pos_amt = pm.get_pos_amt(p_name)
        pos_l_amt = pm.get_pos_amt(p_name, Direction.LONG)
        pos_s_amt = pm.get_pos_amt(p_name, Direction.SHORT)
        direc = pm.get_direc(p_name)
        status = pm.get_status(p_name)

        t_2_origin = pm.get_trading_status_pnum(2)

        if tgt_amt != 0 and (
                (pos_amt == tgt_amt and direc == Direction.LONG) or
                (pos_amt == - tgt_amt and direc == Direction.SHORT)):
            pm.set_open_order(p_name, None)
            self.print_log("====%s: 开仓完成====\n仓名: %s\n" % (self.cta_engine.datetime, p_name))
        elif pos_l_amt == 0 and pos_s_amt == 0:
            pm.set_status(p_name, CLOSE_FINISHED)
            pm.set_special_close(p_name, False)
            pm.set_stop_level(p_name, 0)
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
            self.print_log("=====%s平仓完成=====\n仓名: %s\n" % (self.cta_engine.datetime, p_name))



        # 建完仓，应该把open_order设置为None；
        # 平完仓，应该把两个stop_order设置为None，并将另一个stoporder、cancel掉
        self.print_log(pm.get_pos_data_str(p_name, self.cta_engine.datetime))

        # TODO: 连续孕线处理逻辑。增加on_bar下单条件判断：某一持仓在孕线满足的前提下，是否可以下单。
        # 开仓需要看enabled，平仓不用。这样，禁了以后，如果是持仓，则默默等到平仓；如果平仓，则不会开仓。

        # TODO: 增加一个是否立即强制平仓

        e_0 = pm.get_enabled_status_pnum(0)
        e_1 = pm.get_enabled_status_pnum(1)
        e_2 = pm.get_enabled_status_pnum(2)
        t_0 = pm.get_trading_status_pnum(0)
        t_1 = pm.get_trading_status_pnum(1)
        t_2 = pm.get_trading_status_pnum(2)
        op_key = "0^%s_0^%s_1^%s_1^%s_2^%s_2^%s" % (e_0, t_0, e_1, t_1, e_2, t_2)
        self.print_log(op_key)
        con_op = self.continuous_signal_operations
        op_val = con_op.get(op_key)
        ops = [] if op_val is None else op_val.split("_")
        # TODO: 是在下一根孕线，也就是下一个5分钟线的时候才进行更新。
        # 0号仓在closed条件下不能disable。不不不，应该是，如果要全disable，则至少有一个仓是open状态，否则，ontrade不了，就触发不了0号仓的enable了。
        # 也就是说，如果是3closed状态，那么就不要再把0号仓disable掉了。
        # 任何在在enable的时候，都得是closed状态。不可以enable一个有持仓的仓
        for _op in ops:
            p_num_str, status = _op.split("^")
            pm.set_enabled_status_pnum(int(p_num_str), status)
            self.print_log("Set Position %s %s" %(p_num_str, status))

        # 如果3号单平仓，则2号单直接平仓。
        p_num = int(p_name[0])
        if p_num == 2:
            if t_2_origin != "closed" and t_2 == "closed":
                if pm.get_status("1a") != CLOSE_FINISHED:
                    pm.set_special_close("1a", True)
                    self.print_log(
                        "====%s: 特殊平仓====\n仓名: %s\n状态: %s" % (self.cta_engine.datetime, "1a", pm.get_status("1a")))
                if pm.get_status("1b") != CLOSE_FINISHED:
                    pm.set_special_close("1b", True)
                    self.print_log(
                        "====%s: 特殊平仓====\n仓名: %s\n状态: %s" % (self.cta_engine.datetime, "1b", pm.get_status("1b")))


        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        self.print_log(self.get_stop_order_str(stop_order, self.cta_engine.datetime))


    def get_signal_str(self, dt):
        signal_str = "=====%s: Signal Info=====\nk2O:%s, k2C:%s\nk2H:%s, k2L:%s\nK1H:%s, k1L:%s\nk0A:%s, k0B:%s\n" % (
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

    def get_stop_order_str(self, order: StopOrder, dt):
        order_str = "=====%s: StopOrder=====\n%s, %s\n%s, %s\n%s, %s\n" %(
            dt,
            order.stop_orderid,
            order.status.name,
            order.direction.name,
            order.offset.name,
            order.volume,
            order.price
        )
        return order_str

    def get_order_str(self, order: OrderData, dt):
        order_str = "=====%s: OrderData=====\n%s, %s\n%s, %s\n%s, %s\n" %(
            dt,
            order.vt_orderid,
            order.status.name,
            order.direction.name,
            order.offset.name,
            order.traded,
            order.price
        )
        return order_str

    def print_log(self, msg: str):
        self.write_log(msg)
        print(msg)




class PosManager:
    def __init__(self, symbol, exchange, tgt_amt, stop_levels, names=None):
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
                "enabled": False,
                "tgt_amt": tgt_amt,
                "direc": Direction.LONG,
                "inside_bar_dt": None,
                "status": CLOSE_FINISHED,
                "cost_basis": 0,
                "stop_loss_price": 0,
                "stop_profit_price": 0,
                "init_stop_loss_price": 0,
                "stop_loss_abs_distance": 0,
                "stop_level": 0,
                "open_order": None,
                "stop_loss_order": None,
                "stop_profit_order": None,
                "special_close": False
            } for i in names
        }
        self.__order_pos_map = {}
        self.names = names
        self.a_stop_levels = pd.DataFrame(
            data=[
                [0.8, 0.6, 1.2],
                [1, 0.8, 1.4],
                [1.2, 1, 2]
            ],
            columns=["price_ratio", "stop_loss_ratio", "stop_profit_ratio"],
            index=[1, 2, 3]
        )
        self.a_stop_levels = stop_levels["a"]
        self.b_stop_levels = pd.DataFrame(
            data=[
                [2, 0, 4],
                [3, 1, 6],
                [4, 2, 8]
            ],
            columns=["price_ratio", "stop_loss_ratio", "stop_profit_ratio"],
            index=[1, 2, 3]
        )
        self.b_stop_levels = stop_levels["b"]
        self.b_stop_level_top = {"delta_loss_ratio": 1, "delta_profit_ratio": 2}
        self.b_stop_level_top = stop_levels["b_top"]

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

    def is_enabled(self, name):
        return self.__pos_data[name]["enabled"]

    def set_enabled(self, name, enabled):
        self.__pos_data[name]["enabled"] = enabled

    def set_inside_bar_dt(self, name, dt):
        self.__pos_data[name]["inside_bar_dt"] = dt

    def get_all_inside_bar_dts(self):
        return [self.__pos_data[i]["inside_bar_dt"] for i in self.names]

    def is_gaining_pnum(self, pnum, curr_price):
        a_name = str(pnum) + "a"
        b_name = str(pnum) + "b"
        a_profit = self.get_pos_amt(a_name) * (curr_price - self.get_cost_basis(a_name))
        b_profit = self.get_pos_amt(b_name) * (curr_price - self.get_cost_basis(b_name))
        return a_profit + b_profit > 0

    def set_special_close(self, p_name, special_close):
        self.__pos_data[p_name]["special_close"] = special_close

    def get_special_close(self, p_name):
        return self.__pos_data[p_name]["special_close"]

    def get_enabled_status_pnum(self, pnum):
        a_name = str(pnum) + "a"
        b_name = str(pnum) + "b"
        a_enabled = self.__pos_data[a_name]["enabled"]
        b_enabled = self.__pos_data[b_name]["enabled"]
        res = "other"
        if a_enabled and b_enabled:
            res = "enabled"
        elif not a_enabled and not b_enabled:
            res = "disabled"
        return res

    def set_enabled_status_pnum(self, pnum, status):
        """
        :param pnum:
        :param status: "enabled" "disabled"
        :return:
        """
        assert status in ("enabled", "disabled")
        a_name = str(pnum) + "a"
        b_name = str(pnum) + "b"
        enabled = True if status == "enabled" else False
        self.__pos_data[a_name]["enabled"] = enabled
        self.__pos_data[b_name]["enabled"] = enabled

    def get_trading_status_pnum(self, pnum):
        a_name = str(pnum) + "a"
        b_name = str(pnum) + "b"
        a_status = self.__pos_data[a_name]["status"]
        b_status = self.__pos_data[b_name]["status"]
        res = "other"
        if a_status in (OPEN_FINISHED, CLOSE_STARTED) or b_status in (OPEN_FINISHED, CLOSE_STARTED):
            res = "opened"
        elif a_status == CLOSE_FINISHED and b_status == CLOSE_FINISHED:
            res = "closed"
        return res

    def get_tgt_amt(self, name):
        return self.__pos_data[name]["tgt_amt"]

    def set_tgt_amt(self, name, tgt_amt):
        self.__pos_data[name]["tgt_amt"] = tgt_amt

    def get_stop_loss_abs_distance(self, name):
        return self.__pos_data[name]["stop_loss_abs_distance"]

    def set_stop_loss_abs_distance(self, name, stop_loss_abs_distance):
        self.__pos_data[name]["stop_loss_abs_distance"] = stop_loss_abs_distance

    def get_direc(self, name):
        return self.__pos_data[name]["direc"]

    def set_direc(self, name, direc):
        self.__pos_data[name]["direc"] = direc

    def get_status(self, name):
        return self.__pos_data[name]["status"]

    def set_status(self, name, status):
        self.__pos_data[name]["status"] = status

    def get_stop_level(self, name):
        return self.__pos_data[name]["stop_level"]

    def set_stop_level(self, name, stop_level):
        self.__pos_data[name]["stop_level"] = stop_level

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

    def set_init_stop_loss_price(self, name, stop_loss_price):
        self.__pos_data[name]["init_stop_loss_price"] = stop_loss_price

    def set_stop_prices(self, name, stop_loss_price=None, stop_profit_price=None):
        if stop_loss_price is not None:
            self.__pos_data[name]["stop_loss_price"] = stop_loss_price
        if stop_profit_price is not None:
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
            # self.__pos_data[name]["stop_loss_price"] = 0
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
            # self.__pos_data[name]["stop_profit_price"] = 0
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

    def get_cost_basis(self, p_name):
        return self.__pos_data[p_name]["cost_basis"]
    def update_trade(self, trade):
        print(self.__order_pos_map)
        vt_orderid = ".".join([trade.gateway_name, trade.orderid])
        name = self.__order_pos_map[vt_orderid]  # 理论上一定会有对应的order的。所以，不用get
        pd = self.__pos_data[name]

        ph = self.__pos_holdings[name]
        new_pos_amt = self.get_pos_amt(name) + trade.volume * (1 if trade.direction == Direction.LONG else -1)
        if new_pos_amt == 0:
            cost_basis = 0
        else:
            cost_basis = (
                pd["cost_basis"] * self.get_pos_amt(name) +
                trade.price * trade.volume * (1 if trade.direction == Direction.LONG else -1)
            ) / new_pos_amt
        pd["cost_basis"] = cost_basis
        ph.update_trade(trade)

    def pos_name_of_trade(self, trade):
        vt_orderid = ".".join([trade.gateway_name, trade.orderid])
        name = self.__order_pos_map[vt_orderid]  # 理论上一定会有对应的order的。所以，不用get
        return name

    def pos_name_of_order(self, order):
        vt_orderid = order.vt_orderid
        # 如果是cross_stop_order的话，新的限价单on_order时，不存在对应的order。所以可能会返回None
        name = self.__order_pos_map.get(vt_orderid)
        return name

    def get_pos_data(self):
        return self.__pos_data

    def adjust_stop_prices(self, name, curr_price):
        """
        :param name:
        :param curr_price:
        :param levels: list of float
        :return:
        """
        self.a_stop_levels
        self.b_stop_levels
        self.b_stop_level_top
        pd = self.__pos_data[name]
        cost_basis = pd["cost_basis"]
        stop_level = pd["stop_level"]
        stop_loss_abs_distance = pd["stop_loss_abs_distance"]
        assert stop_loss_abs_distance > 0
        direc = pd["direc"]
        next_level = stop_level + 1
        curr_level = stop_level
        changed = False

        direc_coef = 1 if direc == Direction.LONG else -1

        if "a" in name:
            curr_price_ratio = (curr_price - cost_basis) * direc_coef / stop_loss_abs_distance
            for i in self.a_stop_levels.loc[next_level:].index:
                pr = self.a_stop_levels.get_value(i, "price_ratio")
                if curr_price_ratio >= pr:
                    curr_level = i
                    changed = True
            if changed:
                stop_loss_ratio = self.a_stop_levels.get_value(curr_level, "stop_loss_ratio")
                stop_profit_ratio = self.a_stop_levels.get_value(curr_level, "stop_profit_ratio")
                pd["stop_level"] = curr_level
                pd["stop_loss_price"] = cost_basis + stop_loss_ratio * stop_loss_abs_distance * direc_coef
                pd["stop_profit_price"] = cost_basis + stop_profit_ratio * stop_loss_abs_distance * direc_coef

        else:
            init_stop_loss_price = pd["init_stop_loss_price"]
            curr_price_ratio = (curr_price - cost_basis) / (cost_basis - init_stop_loss_price)
            for i in self.b_stop_levels.loc[next_level:].index:
                pr = self.b_stop_levels.get_value(i, "price_ratio")
                if curr_price_ratio >= pr:
                    curr_level = i
                    changed = True
            top_level = self.b_stop_levels.index[-1]
            top_price_ratio = self.b_stop_levels.price_ratio.iloc[-1]
            if curr_level >= top_level:
                base_price_0 = (cost_basis - init_stop_loss_price) * top_price_ratio + cost_basis
                base_price_1 = base_price_0 + stop_loss_abs_distance * direc_coef * (curr_level - top_level)
                if (curr_price - base_price_1) * direc_coef >= stop_loss_abs_distance:
                    curr_level += (curr_price - base_price_1) * direc_coef // stop_loss_abs_distance
                    changed = True

            if changed:
                pd["stop_level"] = curr_level
                if curr_level <= top_level:
                    stop_loss_ratio = self.b_stop_levels.get_value(curr_level, "stop_loss_ratio")
                    stop_profit_ratio = self.b_stop_levels.get_value(curr_level, "stop_profit_ratio")
                    pd["stop_loss_price"] = cost_basis + stop_loss_ratio * stop_loss_abs_distance * direc_coef
                    pd["stop_profit_price"] = cost_basis + stop_profit_ratio * stop_loss_abs_distance * direc_coef
                else:
                    pd["stop_loss_price"] += \
                        (curr_level - stop_level) * stop_loss_abs_distance * \
                        direc_coef * self.b_stop_level_top["delta_loss_ratio"]
                    pd["stop_profit_price"] += \
                        (curr_level - stop_level) * stop_loss_abs_distance * \
                        direc_coef * self.b_stop_level_top["delta_profit_ratio"]

        return changed

    def get_pos_data_str(self, p_name, dt):
        pd = self.__pos_data[p_name]
        open_order = pd["open_order"]
        open_order_id = open_order if open_order is None else open_order.vt_orderid
        stop_profit_order = pd["stop_profit_order"]
        stop_profit_order_id = stop_profit_order if stop_profit_order is None else stop_profit_order.vt_orderid
        stop_loss_order = pd["stop_loss_order"]
        stop_loss_order_id = None
        if type(stop_loss_order) == OrderData:
            stop_loss_order_id = stop_loss_order.vt_orderid
        elif type(stop_loss_order) == StopOrder:
            stop_loss_order_id = stop_loss_order.stop_orderid

        pos_data_str = \
            "=====%s: Pos Data=====\npos_name: %s\ntgt_amt: %s\nopen_order: %s\ndirec: %s\nstatus: %s\n" \
            "stop_loss_price: %s\nstop_profit_price: %s\nstop_loss_order: %s\nstop_profit_order: %s\ncost_basis: %s\n" \
            "stop_level: %s\nstop_loss_abs_distance: %s\n" %(
                dt,
                p_name,
                pd["tgt_amt"],
                open_order_id,
                pd["direc"],
                pd["status"],
                pd["stop_loss_price"],
                pd["stop_profit_price"],
                stop_loss_order_id,
                stop_profit_order_id,
                pd["cost_basis"],
                pd["stop_level"],
                pd["stop_loss_abs_distance"]
            )
        return pos_data_str

