#!/usr/bin/env python3
"""
✈️  BLR ↔ LIT Live Flight Price Tracker
Uses Sky Scrapper API (RapidAPI) for real Skyscanner prices
Sends email ONLY when round trip drops below $1000
Checks every 6 hours via GitHub Actions — 120 searches/month (within 500 free limit)
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
RAPIDAPI_KEY    = os.environ.get("RAPIDAPI_KEY", "")
RESEND_API_KEY  = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL    = os.environ.get("SENDER_EMAIL", "")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "")

missing = [v for v in ["RAPIDAPI_KEY","RESEND_API_KEY","SENDER_EMAIL","RECIPIENT_EMAIL"] if not os.environ.get(v)]
if missing:
    raise ValueError(f"Missing required secrets: {', '.join(missing)}")

CST         = pytz.timezone("America/Chicago")
STATE_FILE  = "daily_lowest_prices.json"
PRICE_ALERT = 1000

OUTBOUND_DATE = "2026-09-15"
RETURN_DATE   = "2026-12-15"

RAPIDAPI_HOST = "sky-scrapper.p.rapidapi.com"

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
#  ✈️  HARDCODED AIRPORT IDs (saves API calls)
# ─────────────────────────────────────────────
# These were confirmed from previous API calls — no need to look up every time
BLR_SKY_ID    = "BLR"
BLR_ENTITY_ID = "95673351"
LIT_SKY_ID    = "LIT"
LIT_ENTITY_ID = "95674054"


# ─────────────────────────────────────────────
#  ✈️  LIVE FLIGHT SEARCH
# ─────────────────────────────────────────────
def search_live_flights() -> dict:
    """Search real live round trip prices BLR ↔ LIT via Sky Scrapper."""
    log.info("🔍 Searching live BLR ↔ LIT prices via Sky Scrapper...")

    headers = {
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key":  RAPIDAPI_KEY,
    }

    # Use hardcoded airport IDs (confirmed from previous lookups)
    blr_sky, blr_entity = BLR_SKY_ID, BLR_ENTITY_ID
    lit_sky, lit_entity = LIT_SKY_ID, LIT_ENTITY_ID
    log.info(f"✅ Using BLR entityId={blr_entity}, LIT entityId={lit_entity}")

    # Search round trip flights
    url    = "https://sky-scrapper.p.rapidapi.com/api/v1/flights/searchFlights"
    params = {
        "originSkyId":          blr_sky,
        "destinationSkyId":     lit_sky,
        "originEntityId":       blr_entity,
        "destinationEntityId":  lit_entity,
        "date":                 OUTBOUND_DATE,
        "returnDate":           RETURN_DATE,
        "cabinClass":           "economy",
        "adults":               "1",
        "sortBy":               "best",
        "currency":             "USD",
        "market":               "en-US",
        "countryCode":          "US",
    }

    response = requests.get(url, headers=headers, params=params, timeout=30)

    # Handle rate limit gracefully
    if response.status_code == 429:
        log.warning("⚠️ Rate limit hit (429) — too many requests. Will retry next scheduled run.")
        return {"flights": [], "cheapest": None, "outbound": OUTBOUND_DATE, "return_date": RETURN_DATE, "search_url": ""}

    response.raise_for_status()
    data = response.json()

    # Debug — log raw response
    log.info(f"📦 API status: {data.get('status')} | message: {data.get('message')}")
    if "data" in data:
        log.info(f"📦 data keys: {list(data['data'].keys()) if isinstance(data['data'], dict) else type(data['data'])}")

    flights = []
    # Try multiple possible response structures
    itineraries = (
        data.get("data", {}).get("itineraries", []) or
        data.get("data", {}).get("flights", []) or
        data.get("itineraries", []) or
        data.get("flights", []) or
        []
    )
    log.info(f"📦 Itineraries found: {len(itineraries)}")

    for item in itineraries:
        try:
            price     = item.get("price", {}).get("raw", 0)
            legs      = item.get("legs", [])
            if not legs or not price:
                continue

            outbound  = legs[0]
            carriers  = outbound.get("carriers", {}).get("marketing", [])
            airline   = carriers[0].get("name", "Unknown") if carriers else "Unknown"
            dep_time  = outbound.get("departure", "")
            arr_time  = outbound.get("arrival", "")
            duration  = outbound.get("durationInMinutes", 0)
            stops     = outbound.get("stopCount", 0)

            # Get layover info
            segments  = outbound.get("segments", [])
            layovers  = []
            for i, seg in enumerate(segments[:-1]):
                dest = seg.get("destination", {}).get("name", "")
                if dest:
                    layovers.append(dest)
            layover_text = " → ".join(layovers) if layovers else "Direct"

            # Format times
            dep_fmt = dep_time[:16].replace("T", " ") if dep_time else ""
            arr_fmt = arr_time[:16].replace("T", " ") if arr_time else ""
            dur_fmt = f"{duration // 60}h {duration % 60}m" if duration else ""

            flights.append({
                "airline":  airline,
                "price":    int(price),
                "dep_time": dep_fmt,
                "arr_time": arr_fmt,
                "duration": dur_fmt,
                "stops":    stops,
                "layovers": layover_text,
            })
        except:
            continue

    flights.sort(key=lambda x: x["price"])
    cheapest = flights[0]["price"] if flights else None
    log.info(f"✅ Found {len(flights)} flights. Cheapest RT: ${cheapest}")

    return {
        "flights":      flights,
        "cheapest":     cheapest,
        "outbound":     OUTBOUND_DATE,
        "return_date":  RETURN_DATE,
        "search_url":   f"https://www.skyscanner.co.in/transport/flights/bang/lit/{OUTBOUND_DATE.replace('-','')}/{RETURN_DATE.replace('-','')}/?adults=1&cabinclass=economy&rtn=1",
    }


# ─────────────────────────────────────────────
#  📧 EMAIL BUILDER
# ─────────────────────────────────────────────
def build_alert_email(result: dict, now_str: str) -> str:
    flights  = result.get("flights", [])
    cheapest = result.get("cheapest", 0)

    def stops_label(s):
        if s == 0: return "✈ Nonstop"
        if s == 1: return "1 Stop"
        return f"{s} Stops"

    flight_rows = ""
    for i, f in enumerate(flights[:5]):
        is_best     = i == 0
        price_color = "#00c853" if is_best else "#cdd9e8"
        bg          = "background:#060e18;" if is_best else ""
        badge       = "<br><span style='background:#00c85322;color:#00c853;padding:2px 6px;border-radius:4px;font-size:10px;'>⭐ CHEAPEST</span>" if is_best else ""
        flight_rows += f"""
        <tr style="border-bottom:1px solid #1a2a3a;{bg}">
          <td style="padding:14px 10px;">
            <div style="color:#7eb8f7;font-weight:bold;font-size:13px;">{f['airline']}{badge}</div>
            <div style="color:#3d5a7a;font-size:11px;">{stops_label(f['stops'])}</div>
          </td>
          <td style="padding:14px 10px;text-align:center;">
            <div style="font-size:24px;font-weight:900;color:{price_color};">${f['price']}</div>
            <div style="font-size:10px;color:#3d5a7a;">Round Trip</div>
          </td>
          <td style="padding:14px 10px;color:#8aaccc;font-size:12px;">
            <div>🛫 {f['dep_time']}</div>
            <div>🛬 {f['arr_time']}</div>
            <div style="color:#3d5a7a;font-size:11px;">⏱ {f['duration']}</div>
          </td>
          <td style="padding:14px 10px;color:#5a7a9a;font-size:11px;">{f['layovers']}</td>
          <td style="padding:14px 10px;text-align:center;">
            <a href="{result['search_url']}" style="background:#{'00c853' if is_best else '1a3a6a'};color:#{'000' if is_best else '7eb8f7'};padding:8px 14px;border-radius:6px;text-decoration:none;font-size:11px;font-weight:bold;">
              {'🎫 Book' if is_best else 'View'}
            </a>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>body{{margin:0;padding:0;background:#050b14;font-family:'Courier New',monospace;color:#cdd9e8;}}</style>
</head>
<body>
<div style="max-width:700px;margin:0 auto;padding:24px;">

  <div style="text-align:center;padding:28px 0 20px;border-bottom:1px solid #1a2a3a;margin-bottom:24px;">
    <div style="font-size:11px;letter-spacing:5px;color:#4488ff;margin-bottom:8px;">LIVE PRICE ALERT • SKYSCANNER DATA</div>
    <h1 style="margin:0;font-size:26px;font-weight:900;color:#4488ff;">✈ BLR ↔ LITTLE ROCK</h1>
    <div style="color:#3d5a7a;font-size:12px;margin-top:6px;">Bangalore (BLR) ↔ Little Rock, Arkansas (LIT)</div>
    <div style="color:#3d5a7a;font-size:11px;margin-top:4px;">Sep–Dec 2026 • 1 Adult • Round Trip • Economy</div>
    <div style="color:#3d5a7a;font-size:11px;margin-top:2px;">Checked: {now_str}</div>
  </div>

  <div style="background:linear-gradient(135deg,#0d2a0d,#081528);border:2px solid #00c853;border-radius:12px;padding:24px;margin-bottom:24px;text-align:center;">
    <div style="font-size:12px;letter-spacing:4px;color:#00c853;margin-bottom:10px;">🚨 LIVE PRICE ALERT</div>
    <div style="font-size:20px;font-weight:bold;color:white;margin-bottom:8px;">BLR ↔ Little Rock dropped below $1,000!</div>
    <div style="font-size:44px;font-weight:900;color:#00c853;margin:10px 0;">${cheapest}</div>
    <div style="font-size:13px;color:#5a9a5a;margin-bottom:18px;">1 Adult • Round Trip • Economy • Sep–Dec 2026</div>
    <a href="{result['search_url']}" style="background:#00c853;color:#000;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:15px;display:inline-block;">
      🔍 Search on Skyscanner Now
    </a>
  </div>

  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:12px;overflow:hidden;margin-bottom:20px;">
    <div style="padding:14px 16px;border-bottom:1px solid #1a2a3a;">
      <div style="font-size:11px;letter-spacing:3px;color:#4488ff;">📊 TOP 5 CHEAPEST FLIGHTS</div>
      <div style="font-size:11px;color:#3d5a7a;margin-top:4px;">Live data • Outbound: {OUTBOUND_DATE} • Return: {RETURN_DATE}</div>
    </div>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="background:#0a1220;font-size:10px;letter-spacing:1px;color:#3d5a7a;text-transform:uppercase;">
          <th style="padding:10px;text-align:left;">Airline</th>
          <th style="padding:10px;text-align:center;">Price RT</th>
          <th style="padding:10px;text-align:left;">Times</th>
          <th style="padding:10px;text-align:left;">Via</th>
          <th style="padding:10px;text-align:center;">Book</th>
        </tr>
      </thead>
      <tbody>{flight_rows}</tbody>
    </table>
  </div>

  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:10px;padding:16px;margin-bottom:20px;text-align:center;">
    <div style="font-size:11px;letter-spacing:3px;color:#4488ff;margin-bottom:12px;">🔗 SEARCH ON</div>
    <a href="{result['search_url']}" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🛫 Skyscanner</a>
    <a href="https://www.google.com/flights#search;f=BLR;t=LIT;d={OUTBOUND_DATE};r={RETURN_DATE};tt=o;oc=1" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🔍 Google Flights</a>
    <a href="https://www.kayak.co.in/flights/BLR-LIT/{OUTBOUND_DATE}/{RETURN_DATE}?sort=price_a" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">📊 Kayak</a>
    <a href="https://www.makemytrip.com/flights/international/bangalore-to-littlerock/roundtrip" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🇮🇳 MakeMyTrip</a>
  </div>

  <div style="background:#0a1220;border:1px solid #1a2a3a;border-radius:8px;padding:12px;text-align:center;margin-bottom:16px;">
    <div style="color:#3d5a7a;font-size:11px;">🔔 Alert: <strong style="color:#ffab00;">Under $1,000 RT</strong> • Real Skyscanner prices via Sky Scrapper API</div>
  </div>

  <div style="text-align:center;color:#1e2a3a;font-size:10px;letter-spacing:2px;padding-top:16px;border-top:1px solid #0d1520;">
    LIVE FLIGHT TRACKER • BLR↔LIT • SKYSCANNER DATA
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
    log.info("  ✈️  BLR ↔ LIT LIVE FLIGHT TRACKER")
    log.info(f"  🕐  Time: {now_str}")
    log.info(f"  🔔  Alert: under ${PRICE_ALERT} RT")
    log.info(f"  📧  Sending to: {RECIPIENT_EMAIL}")
    log.info("=" * 55)

    state = load_state()
    if state.get("date") != today:
        log.info("📅 New day — resetting state")
        state = {"date": today, "lowest_rt": 9999, "alert_sent_date": None}

    prev_lowest = state.get("lowest_rt", 9999)

    # Fetch live prices
    result   = search_live_flights()
    rt_price = result.get("cheapest")

    if rt_price is None:
        log.warning("⚠️ No flights found — skipping")
        return

    # Update lowest
    if rt_price < prev_lowest:
        log.info(f"📉 New lowest: ${rt_price} RT (was ${prev_lowest})")
        state["lowest_rt"] = rt_price
    save_state(state)

    log.info(f"💰 Live RT: ${rt_price} | Threshold: ${PRICE_ALERT}")

    alert_sent_date = state.get("alert_sent_date")

    # 🚨 Send ONLY when under $1000
    if rt_price < PRICE_ALERT and alert_sent_date != today:
        log.info(f"🚨 PRICE ALERT! ${rt_price} RT is under ${PRICE_ALERT}!")
        subject = f"🚨 BLR↔LIT ALERT: Round trip dropped to ${rt_price}! Book now!"
        html    = build_alert_email(result, now_str)
        send_email(html, subject)
        state["alert_sent_date"] = today
        save_state(state)
        log.info("✅ Alert email sent!")

    elif rt_price < PRICE_ALERT and alert_sent_date == today:
        log.info(f"📵 Alert already sent today — skipping")

    else:
        log.info(f"ℹ️  ${rt_price} RT — above ${PRICE_ALERT} threshold, no email sent")

    log.info("✅ Done!")


if __name__ == "__main__":
    main()
