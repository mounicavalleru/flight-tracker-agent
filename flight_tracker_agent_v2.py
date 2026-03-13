#!/usr/bin/env python3
"""
✈️  BLR → LIT Live Flight Price Tracker
Tracks REAL live prices from Google Flights via SerpApi
Sends email ONLY when actual ticket price drops below $1000
Checks hourly via GitHub Actions
"""

import os
import json
import logging
import requests
import resend
from datetime import datetime
import pytz

# ─────────────────────────────────────────────
#  ⚙️  CONFIGURATION — Set in GitHub Secrets
# ─────────────────────────────────────────────
SERPAPI_KEY     = os.environ.get("SERPAPI_KEY", "")
RESEND_API_KEY  = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL    = os.environ.get("SENDER_EMAIL", "")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "")

missing = [v for v in ["SERPAPI_KEY","RESEND_API_KEY","SENDER_EMAIL","RECIPIENT_EMAIL"] if not os.environ.get(v)]
if missing:
    raise ValueError(f"Missing required secrets: {', '.join(missing)}")

CST         = pytz.timezone("America/Chicago")
STATE_FILE  = "daily_lowest_prices.json"
PRICE_ALERT = 1000  # Alert when RT drops below this

# Travel window — any date Sep–Dec 2026
OUTBOUND_DATE = "2026-09-15"  # Mid-Sep as search date (flexible month)
RETURN_DATE   = "2026-12-15"  # Mid-Dec as return date (flexible month)

# ─────────────────────────────────────────────
#  📋 LOGGING
# ─────────────────────────────────────────────
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
#  ✈️  LIVE FLIGHT SEARCH via SerpApi
# ─────────────────────────────────────────────
def search_live_flights() -> dict:
    """Fetch real live flight prices from Google Flights via SerpApi."""
    log.info("🔍 Searching live flights BLR → LIT via Google Flights...")

    params = {
        "engine":          "google_flights",
        "departure_id":    "BLR",
        "arrival_id":      "LIT",
        "outbound_date":   OUTBOUND_DATE,
        "return_date":     RETURN_DATE,
        "adults":          "1",
        "currency":        "USD",
        "hl":              "en",
        "type":            "1",   # 1 = round trip
        "api_key":         SERPAPI_KEY,
    }

    response = requests.get(
        "https://serpapi.com/search",
        params=params,
        timeout=30
    )
    response.raise_for_status()
    data = response.json()

    # Extract best flights
    flights       = []
    best_flights  = data.get("best_flights", [])
    other_flights = data.get("other_flights", [])
    all_flights   = best_flights + other_flights

    for flight in all_flights:
        price = flight.get("price")
        if not price:
            continue

        # Get outbound leg details
        legs          = flight.get("flights", [])
        outbound_leg  = legs[0] if legs else {}
        airline       = outbound_leg.get("airline", "Unknown")
        flight_number = outbound_leg.get("flight_number", "")
        departure     = outbound_leg.get("departure_airport", {})
        arrival       = outbound_leg.get("arrival_airport", {})
        dep_time      = departure.get("time", "")
        arr_time      = arrival.get("time", "")
        duration      = flight.get("total_duration", 0)
        layovers      = flight.get("layovers", [])
        layover_names = " → ".join([l.get("name", "") for l in layovers]) if layovers else "Direct"
        booking_token = flight.get("booking_token", "")

        # Build Google Flights direct link
        booking_url = (
            f"https://www.google.com/flights#search;f=BLR;t=LIT;"
            f"d={OUTBOUND_DATE};r={RETURN_DATE};tt=o;oc=1"
        )

        flights.append({
            "airline":       airline,
            "flight_number": flight_number,
            "price":         price,
            "dep_time":      dep_time,
            "arr_time":      arr_time,
            "duration_mins": duration,
            "layovers":      layover_names,
            "booking_url":   booking_url,
            "is_best":       flight in best_flights,
        })

    # Sort by price
    flights.sort(key=lambda x: x["price"])

    cheapest = flights[0]["price"] if flights else None
    log.info(f"✅ Found {len(flights)} flights. Cheapest: ${cheapest}")

    return {
        "flights":      flights,
        "cheapest":     cheapest,
        "outbound":     OUTBOUND_DATE,
        "return_date":  RETURN_DATE,
        "search_url":   f"https://www.google.com/flights#search;f=BLR;t=LIT;d={OUTBOUND_DATE};r={RETURN_DATE};tt=o;oc=1",
    }


# ─────────────────────────────────────────────
#  📧 EMAIL BUILDER
# ─────────────────────────────────────────────
def build_html_email(result: dict, now_str: str, is_alert: bool) -> str:
    flights  = result.get("flights", [])
    cheapest = result.get("cheapest", 0)

    def mins_to_hrs(mins):
        if not mins: return "—"
        h, m = divmod(mins, 60)
        return f"{h}h {m}m"

    # Build flight rows — show top 5
    flight_rows = ""
    for i, f in enumerate(flights[:5]):
        is_cheapest = i == 0
        best_badge  = "<span style='background:#00c85322;color:#00c853;padding:2px 6px;border-radius:4px;font-size:10px;'>⭐ CHEAPEST</span>" if is_cheapest else ""
        price_color = "#00c853" if is_cheapest else "#cdd9e8"
        flight_rows += f"""
        <tr style="border-bottom:1px solid #1a2a3a;{'background:#070f1a;' if is_cheapest else ''}">
          <td style="padding:14px 10px;">
            <div style="color:#7eb8f7;font-weight:bold;font-size:13px;">{f['airline']}</div>
            <div style="color:#3d5a7a;font-size:11px;">{f['flight_number']}</div>
            {best_badge}
          </td>
          <td style="padding:14px 10px;text-align:center;">
            <div style="font-size:22px;font-weight:900;color:{price_color};">${f['price']}</div>
            <div style="font-size:10px;color:#3d5a7a;">Round Trip</div>
          </td>
          <td style="padding:14px 10px;color:#8aaccc;font-size:12px;">
            <div>{f['dep_time']} → {f['arr_time']}</div>
            <div style="color:#3d5a7a;font-size:11px;">{mins_to_hrs(f['duration_mins'])}</div>
          </td>
          <td style="padding:14px 10px;color:#5a7a9a;font-size:11px;">{f['layovers']}</td>
          <td style="padding:14px 10px;text-align:center;">
            <a href="{f['booking_url']}" style="background:#{'00c853' if is_cheapest else '1a3a6a'};color:#{'000' if is_cheapest else '7eb8f7'};padding:8px 14px;border-radius:6px;text-decoration:none;font-size:11px;font-weight:bold;display:inline-block;">
              {'🎫 BOOK NOW' if is_cheapest else 'View'}
            </a>
          </td>
        </tr>"""

    alert_banner = ""
    if is_alert:
        alert_banner = f"""
  <div style="background:linear-gradient(135deg,#0d2a0d,#081528);border:2px solid #00c853;border-radius:12px;padding:24px;margin-bottom:24px;text-align:center;">
    <div style="font-size:12px;letter-spacing:4px;color:#00c853;margin-bottom:10px;">🚨 LIVE PRICE ALERT</div>
    <div style="font-size:22px;font-weight:bold;color:white;margin-bottom:8px;">BLR → Little Rock dropped below $1,000!</div>
    <div style="font-size:42px;font-weight:900;color:#00c853;margin:10px 0;">${cheapest}</div>
    <div style="font-size:13px;color:#5a9a5a;margin-bottom:16px;">1 Adult • Round Trip • Sep–Dec 2026</div>
    <a href="{result.get('search_url','')}" style="background:#00c853;color:#000;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:14px;display:inline-block;">
      🔍 Search Live on Google Flights
    </a>
  </div>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>body{{margin:0;padding:0;background:#050b14;font-family:'Courier New',monospace;color:#cdd9e8;}}</style>
</head>
<body>
<div style="max-width:680px;margin:0 auto;padding:24px;">

  <div style="text-align:center;padding:28px 0 20px;border-bottom:1px solid #1a2a3a;margin-bottom:24px;">
    <div style="font-size:11px;letter-spacing:5px;color:#4488ff;margin-bottom:8px;">LIVE FLIGHT TRACKER • GOOGLE FLIGHTS DATA</div>
    <h1 style="margin:0;font-size:26px;font-weight:900;color:#4488ff;">✈ BLR → LITTLE ROCK</h1>
    <div style="color:#3d5a7a;font-size:12px;margin-top:6px;">Bangalore (BLR) → Little Rock, Arkansas (LIT)</div>
    <div style="color:#3d5a7a;font-size:11px;margin-top:4px;">Travel: Sep–Dec 2026 • 1 Adult • Round Trip</div>
    <div style="color:#3d5a7a;font-size:11px;margin-top:2px;">Checked: {now_str}</div>
  </div>

  {alert_banner}

  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:12px;overflow:hidden;margin-bottom:20px;">
    <div style="padding:14px 16px;border-bottom:1px solid #1a2a3a;">
      <div style="font-size:11px;letter-spacing:3px;color:#4488ff;">📊 LIVE FLIGHT PRICES — TOP 5 CHEAPEST</div>
      <div style="font-size:11px;color:#3d5a7a;margin-top:4px;">Real prices from Google Flights • {result.get('outbound','')} → {result.get('return_date','')}</div>
    </div>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="background:#0a1220;font-size:10px;letter-spacing:1px;color:#3d5a7a;text-transform:uppercase;">
          <th style="padding:10px;text-align:left;">Airline</th>
          <th style="padding:10px;text-align:center;">Price</th>
          <th style="padding:10px;text-align:left;">Times</th>
          <th style="padding:10px;text-align:left;">Layover</th>
          <th style="padding:10px;text-align:center;">Book</th>
        </tr>
      </thead>
      <tbody>{flight_rows}</tbody>
    </table>
  </div>

  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:10px;padding:16px;margin-bottom:20px;text-align:center;">
    <div style="font-size:11px;letter-spacing:3px;color:#4488ff;margin-bottom:12px;">🔗 SEARCH DIRECTLY</div>
    <a href="https://www.google.com/flights#search;f=BLR;t=LIT;d={OUTBOUND_DATE};r={RETURN_DATE};tt=o;oc=1" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🔍 Google Flights</a>
    <a href="https://www.skyscanner.co.in/transport/flights/bang/lit/2609/2612/?adultsv2=1&cabinclass=economy&rtn=1" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🛫 Skyscanner</a>
    <a href="https://www.kayak.co.in/flights/BLR-LIT/2026-09-01/2026-12-31?sort=price_a" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">📊 Kayak</a>
    <a href="https://www.makemytrip.com/flights/international/bangalore-to-littlerock/roundtrip" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🇮🇳 MakeMyTrip</a>
  </div>

  <div style="background:#0a1220;border:1px solid #1a2a3a;border-radius:8px;padding:12px;text-align:center;margin-bottom:16px;">
    <div style="color:#3d5a7a;font-size:11px;">🔔 Alert threshold: <strong style="color:#ffab00;">Under $1,000 RT</strong> for 1 adult • Prices from Google Flights</div>
  </div>

  <div style="text-align:center;color:#1e2a3a;font-size:10px;letter-spacing:2px;padding-top:16px;border-top:1px solid #0d1520;">
    LIVE FLIGHT TRACKER • BLR→LIT • DATA FROM GOOGLE FLIGHTS VIA SERPAPI
  </div>
</div>
</body></html>"""


# ─────────────────────────────────────────────
#  📨 SEND EMAIL
# ─────────────────────────────────────────────
def send_email(html_body: str, subject: str):
    resend.api_key = RESEND_API_KEY
    response = resend.Emails.send({
        "from": SENDER_EMAIL,
        "to":   RECIPIENT_EMAIL,
        "subject": subject,
        "html": html_body
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
    checks = state["checks"]

    # Fetch live prices
    result   = search_live_flights()
    rt_price = result.get("cheapest")

    if rt_price is None:
        log.warning("⚠️ No flights found in search results — skipping")
        return

    # Update lowest price
    prev_lowest = state.get("lowest_rt", 9999)
    if rt_price < prev_lowest:
        log.info(f"📉 New lowest today: ${rt_price} RT (was ${prev_lowest})")
        state["lowest_rt"] = rt_price
    save_state(state)

    log.info(f"💰 Live RT: ${rt_price} | Today's lowest: ${state['lowest_rt']} | Threshold: ${PRICE_ALERT}")

    alert_sent_date   = state.get("alert_sent_date")
    morning_sent_date = state.get("morning_sent_date")

    # 🚨 PRICE ALERT — real price under $1000 AND new lowest found today
    if rt_price < PRICE_ALERT and rt_price < prev_lowest:
        log.info(f"🚨 LIVE PRICE ALERT! New lowest ${rt_price} RT is under ${PRICE_ALERT}!")
        subject = f"🚨 LIVE ALERT: BLR→LIT new lowest ${rt_price} RT! Book now!"
        html    = build_html_email(result, now_str, is_alert=True)
        send_email(html, subject)
        state["alert_sent_date"] = today
        save_state(state)
        log.info("✅ Alert email sent!")

    elif rt_price < PRICE_ALERT and alert_sent_date == today and rt_price >= prev_lowest:
        log.info(f"📵 Price ${rt_price} RT is under ${PRICE_ALERT} but not a new low — skipping")

    # 🌅 MORNING EMAIL — first check of day regardless of price
    elif morning_sent_date != today:
        log.info("🌅 Sending morning prices update...")
        subject = f"✈️ BLR→LIT Morning: Cheapest live RT is ${rt_price} | {now.strftime('%b %d')}"
        html    = build_html_email(result, now_str, is_alert=False)
        send_email(html, subject)
        state["morning_sent_date"] = today
        save_state(state)
        log.info("✅ Morning email sent!")

    else:
        log.info(f"ℹ️  ${rt_price} RT — above ${PRICE_ALERT} threshold, no alert needed")

    log.info("✅ Done!")


if __name__ == "__main__":
    main()

