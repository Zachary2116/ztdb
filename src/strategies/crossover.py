import math
import backtrader as bt
from loguru import logger


class QuickScalpMACD(bt.Strategy):
    """
    Quick scalp on 2-minute bars.

    ENTRY (long):
      - MACD line crosses ABOVE signal line (bullish cross)
      - MACD value is BELOW zero (deep pullback)
      - Close price above (or very near) EMA200 (trend filter)
      - RSI < rsi_oversold (default 30) AND rising vs previous bar

    EXIT:
      - Take-profit: +0.20% from entry
      - Stop-loss:   -0.10% from entry
      - OR MACD crosses down
      - OR max_bars_in_trade reached
    """

    params = dict(
        ema_period=200,
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,

        rsi_period=14,
        rsi_oversold=40,        # require RSI < 30 to enter

        risk_per_trade=1.0,    # risk 1% of equity per trade
        tp_pct=0.001,          # +0.20% TP
        sl_pct=0.0010,          # -0.10% SL
        max_bars_in_trade=50,   # 15 * 2min = 30 minutes max

        ema_tolerance=0.005,    # allow price >= EMA * (1 - tol)
    )

    def __init__(self):
        close = self.data.close

        # MACD
        self.macd = bt.ind.MACD(
            close,
            period_me1=self.p.macd_fast,
            period_me2=self.p.macd_slow,
            period_signal=self.p.macd_signal,
        )
        self.cross = bt.ind.CrossOver(self.macd.macd, self.macd.signal)

        # EMA200 trend filter
        self.ema = bt.ind.EMA(close, period=self.p.ema_period)

        # RSI filter
        self.rsi = bt.ind.RSI(close, period=self.p.rsi_period)

        # Simple internal state
        self.in_trade = False
        self.entry_price = None
        self.bars_in_trade = 0

    def _calc_size(self, price: float) -> int:
        """
        Position size based on risk_per_trade and stop distance,
        BUT never more than you can actually afford.
        """
        equity = self.broker.getvalue()
        risk_cap = equity * self.p.risk_per_trade   # $ we’re ok to lose
        sl_dist = price * self.p.sl_pct             # $ distance to stop

        if sl_dist <= 0:
            return 0

        # size based on risk
        raw_risk_size = risk_cap / sl_dist

        # size based on what we can afford
        max_affordable = math.floor(equity / price)

        size = min(raw_risk_size, max_affordable)
        return max(1, math.floor(size))

    def next(self):
        price = float(self.data.close[0])
        ema_val = float(self.ema[0])
        macd_val = float(self.macd.macd[0])
        rsi_val = float(self.rsi[0])

        # previous bar values (for “curling up” checks)
        prev_macd = float(self.macd.macd[-1])
        prev_signal = float(self.macd.signal[-1])
        prev_rsi = float(self.rsi[-1])

        dt = self.data.datetime.datetime(0)

        # track bars in trade
        if self.in_trade:
            self.bars_in_trade += 1
        else:
            self.bars_in_trade = 0

        # ================= ENTRY =================
        if not self.in_trade:
            ema_floor = ema_val * (1 - self.p.ema_tolerance)

            macd_cross_up = self.cross > 0
            macd_below_zero = macd_val < 0
            rsi_oversold_and_rising = (
                rsi_val < self.p.rsi_oversold and rsi_val > prev_rsi
            )
            ema_trend_ok = price >= ema_floor

            buy_condition = (
                macd_cross_up
                and macd_below_zero
                and rsi_oversold_and_rising
                and ema_trend_ok
            )

            if buy_condition:
                size = self._calc_size(price)
                if size <= 0:
                    return

                self.entry_price = price
                self.in_trade = True
                self.buy(size=size)
                logger.info(
                    f"[{dt}] ENTER LONG {size} @ {price:.2f} | "
                    f"MACD={macd_val:.4f} (prev {prev_macd:.4f}) "
                    f"RSI={rsi_val:.2f} (prev {prev_rsi:.2f}) "
                    f"EMA{self.p.ema_period}={ema_val:.2f}"
                )

        # ================= EXIT =================
        else:
            tp_price = self.entry_price * (1 + self.p.tp_pct)
            sl_price = self.entry_price * (1 - self.p.sl_pct)

            exit_reason = None

            if price >= tp_price:
                exit_reason = f"TP hit ({price:.2f} >= {tp_price:.2f})"
            elif price <= sl_price:
                exit_reason = f"SL hit ({price:.2f} <= {sl_price:.2f})"
            elif self.cross < 0:
                exit_reason = "MACD cross down"
            elif self.bars_in_trade >= self.p.max_bars_in_trade:
                exit_reason = f"Max bars in trade reached ({self.bars_in_trade})"

            if exit_reason:
                self.close()
                self.in_trade = False
                logger.info(
                    f"[{dt}] EXIT LONG @ {price:.2f} | "
                    f"{exit_reason} | MACD={macd_val:.4f} RSI={rsi_val:.2f} "
                    f"EMA={ema_val:.2f}"
                )
