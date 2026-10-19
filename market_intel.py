import datetime
import os
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import requests
import yfinance as yf

# Configuration: Pull credentials securely from environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Comprehensive 3-Tier Institutional Asset Map
TIERED_ASSET_CLASSES = {
    "Tier 1: Core Global Macro Barometers": {
        "EUR/USD": "EURUSD=X",
        "USD/JPY": "USDJPY=X",
        "DXY Index": "DX-Y.NYB",
        "2Y UST Futures": "ZT=F",
        "10Y UST Yield": "^TNX",
        "Brent Crude": "BZ=F",
        "Gold Futures": "GC=F",
    },
    "Tier 2: Regional & Credit Overlays": {
        "USD/SGD": "USDSGD=X",
        "USD/CNH": "USDCNH=X",
        "US High Yield ETF (HYG)": "HYG",
    },
    "Tier 3: Macro Risk & Volatility Drivers": {
        "CBOE Volatility Index (VIX)": "^VIX",
        "US TIPS Bond ETF (Inflation Proxy)": "TIP",
    },
}

# Tier 4: Session Macro Catalysts & Event Risk (Update weekly or daily)
TIER_CATALYSTS = [
    "08:30 SGT - AU Retail Sales m/m",
    "14:00 SGT - DE Industrial Production",
    "20:30 SGT - US Core Retail Sales (Tier-1 Print)",
    "22:00 SGT - FOMC Member Speech (Participant Voting)",
]


def fetch_market_data():
  """Pulls historical data across all tiers to compute rolling Z-scores."""
  print(
      "Pulling Comprehensive 4-Tier Quantitative FICC Intelligence Engine..."
  )
  data = {}

  for tier_name, tickers in TIERED_ASSET_CLASSES.items():
    for name, ticker in tickers.items():
      try:
        # Pull 60 days of history to compute robust 20D rolling statistics
        df = yf.download(ticker, period="60d", interval="1d", progress=False)
        if not df.empty:
          close_col = df["Close"] if "Close" in df.columns else df.iloc[:, 0]
          close_series = (
              close_col.iloc[:, 0].dropna()
              if isinstance(close_col, pd.DataFrame)
              else close_col.dropna()
          )

          if len(close_series) >= 20:
            current = float(close_series.iloc[-1].item())
            prev = float(close_series.iloc[-2].item())
            pct_change = ((current - prev) / prev) * 100

            # Quantitative Risk Metric: 20-Day Rolling Z-Score of percentage returns
            pct_returns = close_series.pct_change() * 100
            rolling_mean = pct_returns.rolling(window=20).mean().iloc[-1]
            rolling_std = pct_returns.rolling(window=20).std().iloc[-1]

            z_score = (
                (pct_change - rolling_mean) / rolling_std
                if rolling_std > 0
                else 0.0
            )

            data[name] = {
                "tier": tier_name,
                "price": current,
                "change_pct": pct_change,
                "z_score": float(z_score),
            }
      except Exception as e:
        print(f"Error fetching {name}: {e}")

  return pd.DataFrame.from_dict(data, orient="index")


def send_telegram_message(message: str):
  """Pushes a plain-text message via the Telegram Bot API."""
  if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("Error: Telegram credentials are not set in environment variables.")
    return

  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
  payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}

  try:
    response = requests.post(url, json=payload)
    if response.status_code == 200:
      print("Successfully broadcasted brief to Telegram.")
    else:
      print(f"Failed to send Telegram alert: {response.text}")
  except Exception as e:
    print(f"HTTP Request failed: {e}")


def build_ficc_desk_wire(df):
  """Formats data into a structured 4-tier quantitative desk wire with Z-score alerts."""
  sgt_time = datetime.datetime.now(ZoneInfo("Asia/Singapore"))
  date_str = sgt_time.strftime("%A, %d %b %Y | %H:%M")

  report_lines = [
      "FICC & QUANTITATIVE MACRO DESK WIRE",
      f"TIMESTAMP: {date_str} SGT",
      "----------------------------------------",
  ]

  alerts = []

  for tier_name in TIERED_ASSET_CLASSES.keys():
    tier_data = df[df["tier"] == tier_name]
    if tier_data.empty:
      continue

    report_lines.append(f"\n{tier_name.upper()}")
    for asset, row in tier_data.iterrows():
      sign = "+" if row["change_pct"] > 0 else ""
      z_val = row.get("z_score", 0.0)
      z_str = f" | Z: {z_val:.2f}σ" if not np.isnan(z_val) else ""

      # Format price based on asset standard conventions
      if "USD" in asset or "/" in asset:
        price_str = f"{row['price']:.4f}"
      else:
        price_str = f"{row['price']:.2f}"

      line = f"  - {asset}: {price_str} ({sign}{row['change_pct']:.2f}%{z_str})"
      report_lines.append(line)

      # Statistical Volatility Trigger: Absolute Z-Score > 2.0
      if not np.isnan(z_val) and abs(z_val) > 2.0:
        alerts.append(
            f"ANOMALY DETECTED: {asset} moved {sign}{row['change_pct']:.2f}% ({z_val:.2f}σ from 20D mean)"
        )

  # Append Tier 4: Forward-Looking Macro Catalysts
  report_lines.append("\nTIER 4: SESSION MACRO CATALYSTS & EVENT RISK")
  for catalyst in TIER_CATALYSTS:
    report_lines.append(f"  - {catalyst}")

  report_lines.append("\n----------------------------------------")

  if alerts:
    report_lines.append("\nQUANTITATIVE DESK ALERTS (ABS(Z) > 2.0):")
    report_lines.extend([f"  [!] {alert}" for alert in alerts])
  else:
    report_lines.append(
        "\nDESK STATUS: Volatility contained within normal statistical bands (abs(Z) < 2.0)."
    )

  return "\n".join(report_lines)


if __name__ == "__main__":
  df_market = fetch_market_data()

  if not df_market.empty:
    briefing_text = build_ficc_desk_wire(df_market)

    print("\n--- Generated Master 4-Tier FICC Desk Wire ---\n")
    print(briefing_text)

    # Broadcast live to your Telegram chat
    send_telegram_message(briefing_text)
  else:
    print("Failed to pull any market data.")