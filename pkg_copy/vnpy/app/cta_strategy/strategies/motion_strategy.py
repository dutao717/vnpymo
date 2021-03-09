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

from vnpy.trader.constant import Interval


class MotionStrategy(CtaTemplate):
    """"""

    author = "用Python的交易员"

    atr_value = 0

    ##  孕线策略
    inside_bar_unit = "minute"  ## 1m\1h\1d
    inside_bar_length = 5
    # k0_frequecy = "1m"  ## 1m\1h\1d 直接取回测设置中的周期即可，根据周期判断能否进行回测，并设置k0为相应的数值。



    parameters = [
        "inside_bar_unit",
        "inside_bar_length"
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
        self.amw = ArrayManager()
        self.am = ArrayManager()

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化：" + self.__class__.__name__)
        self.inside_bars = {"k0": 0, "k1": 0, "k2": 0}

        self.k0_last = 0
        self.k1 = {"open": 0, "high": 0, "low": 0, "close": 0}
        self.k2 = {"open": 0, "high": 0, "low": 0, "close": 0}

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
        # self.bg.update_tick(tick)

    def on_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        self.write_log("bar: " + str(bar.datetime))

        self.cancel_all()
        self.bgw.update_bar(bar)
        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        self.k0_last = bar.close_price
        # self.write_log("k0_last: " + str(self.k0_last))

        self.put_event()

    def on_window_bar(self, bar: BarData):

        self.bgw.update_bar(bar)
        self.amw.update_bar(bar)
        self.k2["open"] = self.k1["open"]
        self.k2["high"] = self.k1["high"]
        self.k2["low"] = self.k1["low"]
        self.k2["close"] = self.k1["close"]
        self.k1["open"] = bar.open_price
        self.k1["high"] = bar.high_price
        self.k1["low"] = bar.low_price
        self.k1["close"] = bar.close_price
        self.write_log("w_bar: " + str(bar.datetime))
        # self.write_log("k1: " + str(self.k1))
        # self.write_log("k2: " + str(self.k2))
        self.put_event()
        pass

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        pass

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass
