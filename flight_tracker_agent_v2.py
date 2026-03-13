#!/usr/bin/env python3
"""
✈️  BLR → LIT Live Flight Price Tracker
Uses fast-flights (free, no API key) to get real Google Flights prices
Sends email alert when round trip drops below $1000
Runs every 6 hours via GitHub Actions
"""

import os
import json
import logging
import resend
from datetime import datetime
from fast_flights import FlightData, Passengers, get_flights
import pytz

# ─────────────────────────────────────────────
#  ⚙️  CONFIGURATION — Set in GitHub Secrets
# ─────────────────────────────────────────────
RESEND_API_KEY  = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL    = os.environ.get("SENDER_EMAIL", "")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "")

missing = [v for v in ["RESEND_API_KEY", "SENDER_EMAIL", "RECIPIENT_EMAIL"] if not os.environ.get(v)]
if missing:
    raise ValueError(f"Missing required secrets: {', '.join(missing)}")

CST         = pytz.timezone("America/Chicago")
STATE_FILE  = "daily_lowest_prices.json"
PRICE_ALERT = 1000  # Alert when RT drops below this

# Travel dates — mid Sep outbound, mid Dec return (best price window)
OUTBOUND_DATE = "2026-09-15"
RETURN_DATE   = "2026-12-15"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  💾 STATE
# ─────────────────────────────────────────────
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ─────────────────────────────────────────────
#  ✈️  LIVE FLIGHT SEARCH — fast-flights
# ─────────────────────────────────────────────
def search_live_flights() -> dict:
    """Fetch real live prices from Google Flights using fast-flights library."""
    log.info("🔍 Fetching live BLR → LIT prices from Google Flights...")

    result = get_flights(
        flight_data=[
            FlightData(date=OUTBOUND_DATE, from_airport="BLR", to_airport="LIT"),
            FlightData(date=RETURN_DATE,   from_airport="LIT", to_airport="BLR"),
        ],
        trip="round-trip",
        seat="economy",
        passengers=Passengers(adults=1),
        fetch_mode="fallback",
    )

    flights     = []
    price_level = result.current_price  # "low" / "typical" / "high"

    for f in result.flights:
        # Parse price — remove $ and commas
        try:
            price_str = str(f.price).replace("$", "").replace(",", "").strip()
            price_int = int(float(price_str))
        except:
            continue

        flights.append({
            "airline":   f.name,
            "price":     price_int,
            "departure": str(f.departure),
            "arrival":   str(f.arrival),
            "duration":  str(f.duration),
            "stops":     f.stops,
            "is_best":   getattr(f, "is_best", False),
        })

    # Sort by price
    flights.sort(key=lambda x: x["price"])
    cheapest = flights[0]["price"] if flights else None

    log.info(f"✅ Found {len(flights)} flights. Cheapest: ${cheapest} | Price level: {price_level}")

    return {
        "flights":      flights,
        "cheapest":     cheapest,
        "price_level":  price_level,
        "outbound":     OUTBOUND_DATE,
        "return_date":  RETURN_DATE,
        "search_url":   f"https://www.google.com/flights#search;f=BLR;t=LIT;d={OUTBOUND_DATE};r={RETURN_DATE};tt=o;oc=1",
    }


# ─────────────────────────────────────────────
#  📧 EMAIL BUILDER
# ─────────────────────────────────────────────
def build_html_email(result: dict, now_str: str, is_alert: bool) -> str:
    flights     = result.get("flights", [])
    cheapest    = result.get("cheapest", 0)
    price_level = result.get("price_level", "")
    search_url  = result.get("search_url", "")

    def price_level_badge(level):
        colors = {"low": "#00c853", "typical": "#ffab00", "high": "#ff5252"}
        labels = {"low": "🟢 LOW — Great time to book!", "typical": "🟡 Typical prices", "high": "🔴 High prices"}
        c = colors.get(level, "#4488ff")
        l = labels.get(level, level)
        return f"<span style='background:{c}22;color:{c};padding:4px 12px;border-radius:12px;font-size:12px;font-weight:bold;'>{l}</span>"

    def stops_text(stops):
        if stops == 0: return "Nonstop"
        if stops == 1: return "1 Stop"
        return f"{stops} Stops"

    # Build flight rows — top 5
    flight_rows = ""
    for i, f in enumerate(flights[:5]):
        is_cheapest = i == 0
        price_color = "#00c853" if is_cheapest else "#cdd9e8"
        badge = "<br><span style='background:#00c85322;color:#00c853;padding:2px 6px;border-radius:4px;font-size:10px;'>⭐ CHEAPEST</span>" if is_cheapest else ""
        flight_rows += f"""
        <tr style="border-bottom:1px solid #1a2a3a;{'background:#060e18;' if is_cheapest else ''}">
          <td style="padding:14px 10px;">
            <div style="color:#7eb8f7;font-weight:bold;font-size:13px;">{f['airline']}{badge}</div>
            <div style="color:#3d5a7a;font-size:11px;">{stops_text(f['stops'])}</div>
          </td>
          <td style="padding:14px 10px;text-align:center;">
            <div style="font-size:24px;font-weight:900;color:{price_color};">${f['price']}</div>
            <div style="font-size:10px;color:#3d5a7a;">Round Trip</div>
          </td>
          <td style="padding:14px 10px;color:#8aaccc;font-size:12px;">
            <div>✈ {f['departure']}</div>
            <div>🛬 {f['arrival']}</div>
          </td>
          <td style="padding:14px 10px;color:#5a7a9a;font-size:12px;">{f['duration']}</td>
          <td style="padding:14px 10px;text-align:center;">
            <a href="{search_url}" style="background:#{'00c853' if is_cheapest else '1a3a6a'};color:#{'000' if is_cheapest else '7eb8f7'};padding:8px 14px;border-radius:6px;text-decoration:none;font-size:11px;font-weight:bold;display:inline-block;">
              {'🎫 Book' if is_cheapest else 'View'}
            </a>
          </td>
        </tr>"""

    alert_banner = ""
    if is_alert:
        alert_banner = f"""
  <div style="background:linear-gradient(135deg,#0d2a0d,#081528);border:2px solid #00c853;border-radius:12px;padding:24px;margin-bottom:24px;text-align:center;">
    <div style="font-size:12px;letter-spacing:4px;color:#00c853;margin-bottom:10px;">🚨 PRICE ALERT — REAL GOOGLE FLIGHTS DATA</div>
    <div style="font-size:20px;font-weight:bold;color:white;margin-bottom:8px;">BLR → Little Rock dropped below $1,000!</div>
    <div style="font-size:44px;font-weight:900;color:#00c853;margin:10px 0;">${cheapest}</div>
    <div style="font-size:13px;color:#5a9a5a;margin-bottom:6px;">1 Adult • Round Trip • Economy</div>
    <div style="margin-bottom:18px;">{price_level_badge(price_level)}</div>
    <a href="{search_url}" style="background:#00c853;color:#000;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:15px;display:inline-block;">
      🔍 Search on Google Flights Now
    </a>
  </div>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>body{{margin:0;padding:0;background:#050b14;font-family:'Courier New',monospace;color:#cdd9e8;}}</style>
</head>
<body>
<div style="max-width:700px;margin:0 auto;padding:24px;">

  <div style="text-align:center;padding:28px 0 20px;border-bottom:1px solid #1a2a3a;margin-bottom:24px;">
    <div style="font-size:11px;letter-spacing:5px;color:#4488ff;margin-bottom:8px;">LIVE FLIGHT TRACKER • GOOGLE FLIGHTS DATA</div>
    <h1 style="margin:0;font-size:26px;font-weight:900;color:#4488ff;">✈ BLR → LITTLE ROCK</h1>
    <div style="color:#3d5a7a;font-size:12px;margin-top:6px;">Bangalore (BLR) → Little Rock, Arkansas (LIT)</div>
    <div style="color:#3d5a7a;font-size:11px;margin-top:4px;">Sep–Dec 2026 • 1 Adult • Round Trip • Economy</div>
    <div style="color:#3d5a7a;font-size:11px;margin-top:2px;">Checked: {now_str}</div>
    <div style="margin-top:10px;">{price_level_badge(price_level)}</div>
  </div>

  {alert_banner}

  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:12px;overflow:hidden;margin-bottom:20px;">
    <div style="padding:14px 16px;border-bottom:1px solid #1a2a3a;">
      <div style="font-size:11px;letter-spacing:3px;color:#4488ff;">📊 LIVE PRICES — TOP 5 CHEAPEST FLIGHTS</div>
      <div style="font-size:11px;color:#3d5a7a;margin-top:4px;">Real data from Google Flights • {OUTBOUND_DATE} → {RETURN_DATE}</div>
    </div>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="background:#0a1220;font-size:10px;letter-spacing:1px;color:#3d5a7a;text-transform:uppercase;">
          <th style="padding:10px;text-align:left;">Airline</th>
          <th style="padding:10px;text-align:center;">Price RT</th>
          <th style="padding:10px;text-align:left;">Departure / Arrival</th>
          <th style="padding:10px;text-align:left;">Duration</th>
          <th style="padding:10px;text-align:center;">Book</th>
        </tr>
      </thead>
      <tbody>{flight_rows}</tbody>
    </table>
  </div>

  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:10px;padding:16px;margin-bottom:20px;text-align:center;">
    <div style="font-size:11px;letter-spacing:3px;color:#4488ff;margin-bottom:12px;">🔗 SEARCH DIRECTLY ON</div>
    <a href="{search_url}" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🔍 Google Flights</a>
    <a href="https://www.skyscanner.co.in/transport/flights/bang/lit/2609/2612/?adultsv2=1&cabinclass=economy&rtn=1" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🛫 Skyscanner</a>
    <a href="https://www.kayak.co.in/flights/BLR-LIT/2026-09-15/2026-12-15?sort=price_a" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">📊 Kayak</a>
    <a href="https://www.makemytrip.com/flights/international/bangalore-to-littlerock/roundtrip" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🇮🇳 MakeMyTrip</a>
  </div>

  <div style="background:#0a1220;border:1px solid #1a2a3a;border-radius:8px;padding:12px;text-align:center;margin-bottom:16px;">
    <div style="color:#3d5a7a;font-size:11px;">🔔 Alert threshold: <strong style="color:#ffab00;">Under $1,000 RT</strong> • Data from Google Flights via fast-flights</div>
  </div>

  <div style="text-align:center;color:#1e2a3a;font-size:10px;letter-spacing:2px;padding-top:16px;border-top:1px solid #0d1520;">
    LIVE FLIGHT TRACKER • BLR→LIT • FREE • NO API LIMITS
  </div>
</div>
</body></html>"""


# ─────────────────────────────────────────────
#  📨 SEND EMAIL
# ─────────────────────────────────────────────
def send_email(html_body: str, subject: str):
    resend.api_key = RESEND_API_KEY
    response = resend.Emails.send({
        "from":    SENDER_EMAIL,
        "to":      RECIPIENT_EMAIL,
        "subject": subject,
        "html":    html_body
    })
    log.info(f"📧 Email sent — ID: {response['id']}")


# ─────────────────────────────────────────────
#  🎯 MAIN
# ─────────────────────────────────────────────
def main():
    now     = datetime.now(CST)
    today   = now.strftime("%Y-%m-%d")
    now_str = now.strftime("%A, %B %d at %I:%M %p CST")

    log.info("=" * 55)
    log.info("  ✈️  BLR → LIT LIVE FLIGHT TRACKER")
    log.info(f"  🕐  Time: {now_str}")
    log.info(f"  🔔  Alert: under ${PRICE_ALERT} RT")
    log.info(f"  📧  Sending to: {RECIPIENT_EMAIL}")
    log.info("=" * 55)

    # Load state
    state = load_state()
    if state.get("date") != today:
        log.info("📅 New day — resetting state")
        state = {"date": today, "lowest_rt": 9999, "checks": 0,
                 "alert_sent_date": None, "morning_sent_date": None}

    state["checks"] = state.get("checks", 0) + 1
    prev_lowest = state.get("lowest_rt", 9999)

    # Fetch live prices
    result   = search_live_flights()
    rt_price = result.get("cheapest")

    if rt_price is None:
        log.warning("⚠️ No flights found — skipping")
        return

    # Update lowest
    if rt_price < prev_lowest:
        log.info(f"📉 New lowest today: ${rt_price} (was ${prev_lowest})")
        state["lowest_rt"] = rt_price
    save_state(state)

    log.info(f"💰 Live RT: ${rt_price} | Today's lowest: ${state['lowest_rt']} | Threshold: ${PRICE_ALERT}")

    alert_sent_date   = state.get("alert_sent_date")
    morning_sent_date = state.get("morning_sent_date")

    # 🚨 PRICE ALERT — ONLY send when live price is under $1000
    if rt_price < PRICE_ALERT and alert_sent_date != today:
        log.info(f"🚨 PRICE ALERT! ${rt_price} RT is under ${PRICE_ALERT} — sending email!")
        subject = f"🚨 BLR→LIT PRICE ALERT: Round trip dropped to ${rt_price}! Book now!"
        html    = build_html_email(result, now_str, is_alert=True)
        send_email(html, subject)
        state["alert_sent_date"] = today
        save_state(state)
        log.info("✅ Alert email sent!")

    elif rt_price < PRICE_ALERT and alert_sent_date == today:
        log.info(f"📵 Alert already sent today for ${rt_price} RT — skipping")

    else:
        log.info(f"ℹ️  ${rt_price} RT — above ${PRICE_ALERT} threshold, no email sent")

    log.info("✅ Done!")


if __name__ == "__main__":
    main()
