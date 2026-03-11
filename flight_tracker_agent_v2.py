#!/usr/bin/env python3
"""
✈️  BLR → LIT Flight Price Tracker
Tracks Bangalore → Little Rock round trip for 1 adult
Checks every hour via GitHub Actions
Sends INSTANT email alert when price drops below $1000
Powered by Groq LLaMA 3.3 (Free) + Resend (Free)
"""

import os
import json
import logging
from datetime import datetime
import pytz
from groq import Groq
import resend

# ─────────────────────────────────────────────
#  ⚙️  CONFIGURATION — Set in GitHub Secrets
# ─────────────────────────────────────────────
GROQ_API_KEY    = os.environ.get("GROQ_API_KEY")
RESEND_API_KEY  = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL    = os.environ.get("SENDER_EMAIL", "")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "")

missing = [v for v in ["GROQ_API_KEY","RESEND_API_KEY","SENDER_EMAIL","RECIPIENT_EMAIL"] if not os.environ.get(v)]
if missing:
    raise ValueError(f"Missing required secrets: {', '.join(missing)}")

groq_client = Groq(api_key=GROQ_API_KEY)

CST            = pytz.timezone("America/Chicago")
STATE_FILE     = "daily_lowest_prices.json"
PRICE_ALERT    = 1000   # Send alert when RT drops below this


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
#  🤖 AI RESEARCH
# ─────────────────────────────────────────────
def research_flights() -> dict:
    log.info("🤖 Researching BLR → LIT flight prices...")
    now_str = datetime.now(CST).strftime("%A, %B %d, %Y")

    prompt = f"""Research the cheapest round trip flight prices for 1 adult from Bangalore (BLR) to Little Rock, Arkansas (LIT) for travel between September and December 2026.

Find the absolute cheapest round trip options. Consider all airlines, layovers, and booking windows.
Today's date: {now_str}.

Respond with ONLY valid JSON (no markdown, no backticks):
{{
  "route": "BLR to LIT",
  "round_trip_min": 850,
  "round_trip_max": 1400,
  "one_way_min": 500,
  "one_way_max": 800,
  "recommended_airlines": ["Air India", "American Airlines"],
  "best_layovers": ["Dubai", "London", "Dallas"],
  "best_travel_months": ["September", "October"],
  "best_booking_window": "Book 3-4 months in advance",
  "deal_score": 7,
  "price_trend": "dropping",
  "tip": "Cheapest if booked now before summer demand rises",
  "summary": "2 sentence summary of current prices and deals"
}}"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    data = json.loads(raw.strip())
    log.info(f"✅ Research complete. RT price: ${data.get('round_trip_min')} – ${data.get('round_trip_max')}")
    return data


# ─────────────────────────────────────────────
#  📧 EMAIL BUILDER
# ─────────────────────────────────────────────
def build_html_email(data: dict, price: int, now_str: str, checks: int, is_alert: bool) -> str:

    def deal_color(score):
        if score >= 8: return "#00c853"
        if score >= 6: return "#ffab00"
        return "#ff5252"

    def trend_arrow(trend):
        return {"dropping": "📉 Dropping", "rising": "📈 Rising", "stable": "➡️ Stable"}.get(trend, "➡️ Stable")

    airlines = ", ".join(data.get("recommended_airlines", []))
    layovers = ", ".join(data.get("best_layovers", []))
    months   = ", ".join(data.get("best_travel_months", []))
    score    = data.get("deal_score", 7)

    alert_banner = ""
    if is_alert:
        alert_banner = f"""
  <div style="background:linear-gradient(135deg,#0d2a0d,#0a1f0a);border:2px solid #00c853;border-radius:12px;padding:20px;margin-bottom:20px;text-align:center;">
    <div style="font-size:13px;letter-spacing:3px;color:#00c853;margin-bottom:8px;">🚨 PRICE ALERT TRIGGERED</div>
    <div style="font-size:22px;font-weight:bold;color:white;">BLR → Little Rock dropped below $1,000!</div>
    <div style="font-size:36px;font-weight:900;color:#00c853;margin:10px 0;">${price} Round Trip</div>
    <div style="font-size:13px;color:#5a9a5a;">For 1 Adult • Sep–Dec 2026</div>
  </div>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>body{{margin:0;padding:0;background:#050b14;font-family:'Courier New',monospace;color:#cdd9e8;}}</style>
</head>
<body>
<div style="max-width:600px;margin:0 auto;padding:24px;">

  <div style="text-align:center;padding:30px 0 20px;border-bottom:1px solid #1a2a3a;margin-bottom:24px;">
    <div style="font-size:11px;letter-spacing:5px;color:#4488ff;margin-bottom:8px;">AI FLIGHT TRACKER • AUTOMATED ALERT</div>
    <h1 style="margin:0;font-size:26px;font-weight:900;color:#4488ff;">✈ BLR → LITTLE ROCK</h1>
    <div style="color:#3d5a7a;font-size:12px;margin-top:6px;">Bangalore (BLR) → Little Rock, Arkansas (LIT)</div>
    <div style="color:#3d5a7a;font-size:11px;margin-top:4px;">Checked at: {now_str} • Check #{checks} today</div>
  </div>

  {alert_banner}

  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:12px;padding:20px;margin-bottom:20px;">
    <div style="font-size:11px;letter-spacing:3px;color:#4488ff;margin-bottom:16px;">💰 CURRENT PRICES — 1 ADULT</div>
    <table style="width:100%;border-collapse:collapse;">
      <tr style="border-bottom:1px solid #1a2a3a;">
        <td style="padding:12px 8px;color:#7eb8f7;font-size:13px;">Round Trip</td>
        <td style="padding:12px 8px;text-align:right;">
          <span style="font-size:28px;font-weight:bold;color:{'#00c853' if price <= PRICE_ALERT else '#ccc'};">${data['round_trip_min']}</span>
          <span style="color:#3d5a7a;font-size:12px;"> – ${data['round_trip_max']}</span>
        </td>
      </tr>
      <tr style="border-bottom:1px solid #1a2a3a;">
        <td style="padding:12px 8px;color:#7eb8f7;font-size:13px;">One Way</td>
        <td style="padding:12px 8px;text-align:right;">
          <span style="font-size:22px;font-weight:bold;color:#ccc;">${data['one_way_min']}</span>
          <span style="color:#3d5a7a;font-size:12px;"> – ${data['one_way_max']}</span>
        </td>
      </tr>
      <tr style="border-bottom:1px solid #1a2a3a;">
        <td style="padding:12px 8px;color:#7eb8f7;font-size:13px;">Price Trend</td>
        <td style="padding:12px 8px;text-align:right;color:#ccc;font-size:14px;">{trend_arrow(data.get('price_trend','stable'))}</td>
      </tr>
      <tr style="border-bottom:1px solid #1a2a3a;">
        <td style="padding:12px 8px;color:#7eb8f7;font-size:13px;">Deal Score</td>
        <td style="padding:12px 8px;text-align:right;">
          <span style="background:{deal_color(score)}22;color:{deal_color(score)};padding:4px 12px;border-radius:12px;font-size:13px;font-weight:bold;">{score}/10</span>
        </td>
      </tr>
      <tr style="border-bottom:1px solid #1a2a3a;">
        <td style="padding:12px 8px;color:#7eb8f7;font-size:13px;">Best Airlines</td>
        <td style="padding:12px 8px;text-align:right;color:#ccc;font-size:12px;">{airlines}</td>
      </tr>
      <tr style="border-bottom:1px solid #1a2a3a;">
        <td style="padding:12px 8px;color:#7eb8f7;font-size:13px;">Best Layovers</td>
        <td style="padding:12px 8px;text-align:right;color:#ccc;font-size:12px;">{layovers}</td>
      </tr>
      <tr>
        <td style="padding:12px 8px;color:#7eb8f7;font-size:13px;">Best Months</td>
        <td style="padding:12px 8px;text-align:right;color:#ccc;font-size:12px;">{months}</td>
      </tr>
    </table>
  </div>

  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:10px;padding:16px;margin-bottom:20px;">
    <div style="font-size:11px;letter-spacing:3px;color:#4488ff;margin-bottom:10px;">💡 BOOKING TIP</div>
    <div style="font-size:13px;color:#8aaccc;line-height:1.7;">{data.get('tip','')}</div>
  </div>

  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:10px;padding:16px;margin-bottom:20px;">
    <div style="font-size:11px;letter-spacing:3px;color:#4488ff;margin-bottom:10px;">📝 SUMMARY</div>
    <div style="font-size:13px;color:#8aaccc;line-height:1.7;">{data.get('summary','')}</div>
  </div>

  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:10px;padding:16px;margin-bottom:20px;">
    <div style="font-size:11px;letter-spacing:3px;color:#4488ff;margin-bottom:12px;">🔗 BOOK NOW</div>
    <a href="https://www.google.com/flights#search;f=BLR;t=LIT" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🔍 Google Flights</a>
    <a href="https://www.skyscanner.co.in/transport/flights/bang/lit/" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🛫 Skyscanner</a>
    <a href="https://www.kayak.co.in/flights/BLR-LIT" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">📊 Kayak</a>
    <a href="https://www.makemytrip.com/flights/international" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🇮🇳 MakeMyTrip</a>
  </div>

  <div style="background:#0a1220;border:1px solid #1a2a3a;border-radius:8px;padding:12px;text-align:center;margin-bottom:16px;">
    <div style="color:#3d5a7a;font-size:11px;">🔔 Alert threshold: Under <strong style="color:#ffab00;">$1,000 RT</strong> for 1 adult</div>
  </div>

  <div style="text-align:center;color:#1e2a3a;font-size:10px;letter-spacing:2px;padding-top:16px;border-top:1px solid #0d1520;">
    AI FLIGHT TRACKER • BLR→LIT • PRICES ARE AI ESTIMATES — VERIFY BEFORE BOOKING
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
        "to": RECIPIENT_EMAIL,
        "subject": subject,
        "html": html_body
    })
    log.info(f"📧 Email sent — ID: {response['id']}")


# ─────────────────────────────────────────────
#  🎯 MAIN — runs every hour via GitHub Actions
# ─────────────────────────────────────────────
def main():
    now     = datetime.now(CST)
    today   = now.strftime("%Y-%m-%d")
    now_str = now.strftime("%A, %B %d at %I:%M %p CST")

    log.info("=" * 55)
    log.info("  ✈️  BLR → LIT FLIGHT TRACKER")
    log.info(f"  🕐  Time: {now_str}")
    log.info(f"  🔔  Alert threshold: under ${PRICE_ALERT} RT")
    log.info(f"  📧  Sending to: {RECIPIENT_EMAIL}")
    log.info("=" * 55)

    # Load state
    state = load_state()
    if state.get("date") != today:
        log.info(f"📅 New day — resetting state")
        state = {"date": today, "lowest_rt": 9999, "checks": 0, "alert_sent": False}

    state["checks"] = state.get("checks", 0) + 1
    checks = state["checks"]

    # Research prices
    data     = research_flights()
    rt_price = data.get("round_trip_min", 9999)

    # Update lowest price found today
    prev_lowest = state.get("lowest_rt", 9999)
    if rt_price < prev_lowest:
        log.info(f"📉 New lowest today: ${rt_price} RT (was ${prev_lowest})")
        state["lowest_rt"] = rt_price
    save_state(state)

    log.info(f"💰 Current RT: ${rt_price} | Today's lowest: ${state['lowest_rt']} | Threshold: ${PRICE_ALERT}")

    # ── PRICE ALERT — send immediately if under $1000 ──
    # Alert resets daily — only 1 alert per day max
    alert_sent_date = state.get("alert_sent_date")

    if rt_price < PRICE_ALERT and alert_sent_date != today:
        log.info(f"🚨 PRICE ALERT! ${rt_price} is under ${PRICE_ALERT} threshold — sending email!")
        subject = f"🚨 BLR→LIT PRICE ALERT: Round trip dropped to ${rt_price}! Book now!"
        html    = build_html_email(data, rt_price, now_str, checks, is_alert=True)
        send_email(html, subject)
        state["alert_sent_date"] = today
        save_state(state)
        log.info("✅ Alert email sent!")

    elif rt_price < PRICE_ALERT and alert_sent_date == today:
        log.info(f"📵 Alert already sent today for ${rt_price} RT — skipping")

    else:
        log.info(f"ℹ️  ${rt_price} RT — above ${PRICE_ALERT} threshold, no alert needed")
        # Always send a morning prices email on first check of the day
        morning_sent_date = state.get("morning_sent_date")
        if morning_sent_date != today:
            log.info("🌅 Sending morning prices email")
            subject = f"✈️ BLR→LIT Morning Update: Round trip from ${rt_price} | {now.strftime('%b %d')}"
            html    = build_html_email(data, rt_price, now_str, checks, is_alert=False)
            send_email(html, subject)
            state["morning_sent_date"] = today
            save_state(state)
            log.info("✅ Morning email sent!")
        else:
            log.info("📵 Morning email already sent today — no email needed")

    log.info("✅ Done!")


if __name__ == "__main__":
    main()
