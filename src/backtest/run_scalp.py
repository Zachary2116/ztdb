import argparse
import pandas as pd
import yfinance as yf
import backtrader as bt
from loguru import logger

from src.strategies.crossover import QuickScalpMACD


def download_data(ticker: str, period: str = "30d") -> pd.DataFrame:
    """
    Download intraday data for scalping.
    Default: ~30 days, 2-minute bars.
    """
    logger.info(f"Downloading {ticker} | period={period}, interval=2m")
    df = yf.download(
        ticker,
        period=period,
        interval="2m",
        auto_adjust=True,
    )

    if df.empty:
        raise RuntimeError(f"No data for {ticker}")

    # yfinance can return MultiIndex columns (e.g. Price / Ticker)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    wanted = ["Open", "High", "Low", "Close", "Volume"]
    df = df[wanted]

    return df


def main(ticker: str, cash: float, period: str):
    # 1) get history
    df = download_data(ticker, period)

    # 2) wrap for Backtrader as 2-minute bars
    data_feed = bt.feeds.PandasData(
        dataname=df,
        timeframe=bt.TimeFrame.Minutes,
        compression=2,
    )

    # 3) engine
    cerebro = bt.Cerebro()
    cerebro.adddata(data_feed)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=0.0005)  # 5 bps

    # 4) quick scalp strategy (EMA200 + MACD only)
    cerebro.addstrategy(QuickScalpMACD)

    # 5) run
    start_val = cerebro.broker.getvalue()
    logger.info(f"Starting Portfolio Value: {start_val:,.2f}")

    cerebro.run()

    end_val = cerebro.broker.getvalue()
    logger.info(f"Final   Portfolio Value: {end_val:,.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="SPY")
    ap.add_argument("--cash", type=float, default=25_000)
    ap.add_argument("--period", default="30d")  # 2m bars for ~30 days
    args = ap.parse_args()

    main(
        ticker=args.ticker,
        cash=args.cash,
        period=args.period,
    )
