#!/usr/bin/env python3
"""
✈️  BLR → USA Flight Price Hunter — Automated Agent
Runs daily at 2:30 AM CST, with extra focus on Tue/Wed
Sends results to recipient email
Powered by Groq LLaMA 3.3 (Free)
"""

import os
import json
import schedule
import time
import logging
from datetime import datetime
import pytz
from groq import Groq
import resend

# ─────────────────────────────────────────────
#  ⚙️  CONFIGURATION — Set in Railway Variables
# ─────────────────────────────────────────────
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY")
RESEND_API_KEY   = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL     = os.environ.get("SENDER_EMAIL", "")
RECIPIENT_EMAIL  = os.environ.get("RECIPIENT_EMAIL", "")

# Validate required environment variables
missing = []
if not GROQ_API_KEY:     missing.append("GROQ_API_KEY")
if not RESEND_API_KEY:   missing.append("RESEND_API_KEY")
if not SENDER_EMAIL:     missing.append("SENDER_EMAIL")
if not RECIPIENT_EMAIL:  missing.append("RECIPIENT_EMAIL")
if missing:
    raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

# Configure Groq client
groq_client = Groq(api_key=GROQ_API_KEY)

# ─────────────────────────────────────────────
#  📍 ROUTES
# ─────────────────────────────────────────────
ROUTES = [
    {"city": "Los Angeles",   "state": "California", "code": "LAX", "emoji": "🌴"},
    {"city": "San Francisco", "state": "California", "code": "SFO", "emoji": "🌉"},
    {"city": "Dallas",        "state": "Texas",      "code": "DFW", "emoji": "🤠"},
    {"city": "Houston",       "state": "Texas",      "code": "IAH", "emoji": "🚀"},
    {"city": "New York",      "state": "New York",   "code": "JFK", "emoji": "🗽"},
    {"city": "Little Rock",   "state": "Arkansas",   "code": "LIT", "emoji": "🌿"},
]

# ─────────────────────────────────────────────
#  🇺🇸 DOMESTIC ROUTES
# ─────────────────────────────────────────────
DOMESTIC_ROUTES = [
    {"from_city": "Little Rock",   "from_code": "LIT", "to_city": "San Francisco", "to_code": "SFO", "emoji": "🌿→🌉"},
    {"from_city": "San Francisco", "from_code": "SFO", "to_city": "Little Rock",   "to_code": "LIT", "emoji": "🌉→🌿"},
]

CST = pytz.timezone("America/Chicago")

# ─────────────────────────────────────────────
#  📋 LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("flight_tracker.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  🤖 AI RESEARCH
# ─────────────────────────────────────────────
def research_flights(is_tue_wed: bool) -> dict:
    """Call Groq AI to research current flight prices."""
    log.info("🤖 Starting AI flight research with Groq...")

    focus_note = (
        "IMPORTANT: Today is Tuesday or Wednesday — these are historically the CHEAPEST days "
        "to book flights. Highlight any extra savings available for booking TODAY."
        if is_tue_wed else
        "Note: Tuesday and Wednesday tend to have the cheapest fares — flag if any deals "
        "should be held for those days."
    )

    prompt = f"""Research flight prices from Bangalore (BLR) to these US destinations for September-December 2026:
Los Angeles (LAX), San Francisco (SFO), Dallas (DFW), Houston (IAH), New York (JFK), Little Rock (LIT).

{focus_note}

Compare one-way vs round-trip. Find the absolute cheapest options. Consider airline sales,
seasonal demand dips, and booking windows. Today's date: {datetime.now(CST).strftime('%A, %B %d, %Y')}.

Respond with ONLY valid JSON (no markdown, no backticks):
{{
  "research_date": "YYYY-MM-DD",
  "day_of_week": "Tuesday",
  "is_prime_booking_day": true,
  "routes": [
    {{
      "destination": "LAX",
      "city": "Los Angeles",
      "state": "California",
      "one_way_min": 650,
      "one_way_max": 950,
      "round_trip_min": 900,
      "round_trip_max": 1400,
      "best_months": ["June", "September"],
      "cheapest_option": "round_trip",
      "savings_vs_oneway": 120,
      "recommended_airlines": ["Air India", "Emirates", "Qatar Airways"],
      "best_layover": "Dubai",
      "deal_score": 7,
      "price_trend": "dropping",
      "tip": "Book now - prices expected to rise after March"
    }}
  ],
  "overall_cheapest": "LAX",
  "best_travel_window": "September 1-15 or Dec 5-20",
  "price_alert": "Any notable deals or price drops worth highlighting",
  "summary": "2-3 sentence overall summary",
  "booking_tips": ["tip1", "tip2", "tip3", "tip4"]
}}"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500
    )
    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    data = json.loads(raw.strip())
    log.info(f"✅ Research complete. Cheapest destination: {data.get('overall_cheapest')}")
    return data


# ─────────────────────────────────────────────
#  🇺🇸 DOMESTIC FLIGHT RESEARCH
# ─────────────────────────────────────────────
def research_domestic_flights() -> dict:
    """Call Groq AI to research LIT ↔ SFO domestic flight prices."""
    log.info("🤖 Starting domestic flight research (LIT ↔ SFO)...")

    prompt = f"""Research domestic flight prices SPECIFICALLY for May 10-20, 2026 (NOT any other dates) for these two US routes:
1. Little Rock (LIT) → San Francisco (SFO)
2. San Francisco (SFO) → Little Rock (LIT)

IMPORTANT: Travel dates are strictly May 10-20, 2026 only. You MUST use only "May" in best_months field. Do NOT use September or any other month.

Find cheapest one-way fares, best travel days, and airlines.
Today's date: {datetime.now(CST).strftime('%A, %B %d, %Y')}.

Respond with ONLY valid JSON (no markdown, no backticks):
{{
  "domestic_routes": [
    {{
      "from_code": "LIT",
      "from_city": "Little Rock",
      "to_code": "SFO",
      "to_city": "San Francisco",
      "one_way_min": 200,
      "one_way_max": 450,
      "best_months": ["May"],
      "recommended_airlines": ["American Airlines", "United"],
      "deal_score": 7,
      "price_trend": "stable",
      "tip": "Book 3-4 weeks in advance for best fares"
    }},
    {{
      "from_code": "SFO",
      "from_city": "San Francisco",
      "to_code": "LIT",
      "to_city": "Little Rock",
      "one_way_min": 200,
      "one_way_max": 450,
      "best_months": ["May"],
      "recommended_airlines": ["American Airlines", "United"],
      "deal_score": 7,
      "price_trend": "stable",
      "tip": "Tuesday/Wednesday departures tend to be cheapest"
    }}
  ],
  "domestic_summary": "Brief summary of both routes"
}}"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800
    )
    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    data = json.loads(raw.strip())
    log.info("✅ Domestic research complete.")
    return data


# ─────────────────────────────────────────────
#  📧 EMAIL BUILDER
# ─────────────────────────────────────────────
def build_html_email(data: dict, is_tue_wed: bool, domestic_data: dict = None) -> str:
    """Build a beautiful HTML email from the research data."""
    now_cst = datetime.now(CST).strftime("%A, %B %d, %Y at %I:%M %p CST")
    cheapest = next((r for r in data["routes"] if r["destination"] == data["overall_cheapest"]), data["routes"][0])

    def deal_color(score):
        if score >= 8: return "#00c853"
        if score >= 6: return "#ffab00"
        return "#ff5252"

    def trend_arrow(trend):
        arrows = {"dropping": "📉 Dropping", "rising": "📈 Rising", "stable": "➡️ Stable"}
        return arrows.get(trend, "➡️ Stable")

    rows = ""
    for r in sorted(data["routes"], key=lambda x: x["round_trip_min"]):
        dest = next((d for d in ROUTES if d["code"] == r["destination"]), {})
        emoji = dest.get("emoji", "✈️")
        badge = "🏆 BEST DEAL" if r["destination"] == data["overall_cheapest"] else ""
        rows += f"""
        <tr style="border-bottom:1px solid #1e2a3a;">
          <td style="padding:14px 10px;color:#7eb8f7;font-weight:bold;">
            {emoji} {r['city']}<br>
            <span style="font-size:11px;color:#3d5a7a;">{r['state']} • {r['destination']}</span>
            {"<br><span style='font-size:11px;background:#1a3a1a;color:#00c853;padding:2px 6px;border-radius:4px;'>" + badge + "</span>" if badge else ""}
          </td>
          <td style="padding:14px 10px;text-align:center;">
            <div style="font-size:20px;font-weight:bold;color:{'#00c853' if r['cheapest_option']=='one_way' else '#ccc'};">${r['one_way_min']}</div>
            <div style="font-size:11px;color:#3d5a7a;">up to ${r['one_way_max']}</div>
            {"<div style='font-size:10px;color:#00c853;'>✅ CHEAPER</div>" if r['cheapest_option']=='one_way' else ""}
          </td>
          <td style="padding:14px 10px;text-align:center;">
            <div style="font-size:20px;font-weight:bold;color:{'#00c853' if r['cheapest_option']=='round_trip' else '#ccc'};">${r['round_trip_min']}</div>
            <div style="font-size:11px;color:#3d5a7a;">up to ${r['round_trip_max']}</div>
            {"<div style='font-size:10px;color:#00c853;'>✅ CHEAPER</div>" if r['cheapest_option']=='round_trip' else ""}
          </td>
          <td style="padding:14px 10px;text-align:center;">
            <span style="background:{deal_color(r['deal_score'])}22;color:{deal_color(r['deal_score'])};padding:4px 10px;border-radius:12px;font-size:12px;font-weight:bold;">{r['deal_score']}/10</span>
          </td>
          <td style="padding:14px 10px;color:#7eb8f7;font-size:12px;">{trend_arrow(r.get('price_trend','stable'))}</td>
          <td style="padding:14px 10px;color:#5a7a9a;font-size:11px;">{', '.join(r.get('best_months', ['June'])[:2])}</td>
        </tr>
        <tr style="border-bottom:2px solid #0d1929;background:#070d18;">
          <td colspan="6" style="padding:6px 10px 12px 10px;color:#5a7a9a;font-size:11px;font-style:italic;">
            ✈ {r['recommended_airlines'][0] if r.get('recommended_airlines') else 'Check airlines'} via {r.get('best_layover','—')} &nbsp;|&nbsp; 💡 {r.get('tip','')}
          </td>
        </tr>"""

    tips_html = "".join([
        f'<div style="display:flex;gap:10px;margin-bottom:10px;font-size:13px;color:#8aaccc;"><span style="color:#1e6eff;min-width:22px;font-weight:bold;">{i+1}.</span><span>{tip}</span></div>'
        for i, tip in enumerate(data.get("booking_tips", []))
    ])

    prime_banner = ""
    if is_tue_wed:
        prime_banner = """
        <div style="background:linear-gradient(135deg,#0d2a0d,#0a1f0a);border:1px solid #00c85344;border-radius:10px;padding:16px;margin-bottom:20px;text-align:center;">
          <div style="font-size:11px;letter-spacing:3px;color:#00c853;margin-bottom:6px;">⚡ PRIME BOOKING DAY</div>
          <div style="font-size:15px;color:white;font-weight:bold;">Today is a Tuesday/Wednesday — Airlines often post lowest fares today!</div>
          <div style="font-size:12px;color:#5a9a5a;margin-top:4px;">This is the best time to book your BLR → USA flight.</div>
        </div>"""

    # Build domestic rows
    domestic_rows = ""
    domestic_summary = "No domestic data available."
    if domestic_data:
        domestic_summary = domestic_data.get("domestic_summary", "")
        for r in domestic_data.get("domestic_routes", []):
            domestic_rows += f"""
        <tr style="border-bottom:1px solid #1e2a3a;">
          <td style="padding:14px 10px;color:#ffab00;font-weight:bold;">
            {r['from_code']} → {r['to_code']}<br>
            <span style="font-size:11px;color:#3d5a7a;">{r['from_city']} → {r['to_city']}</span>
          </td>
          <td style="padding:14px 10px;text-align:center;">
            <div style="font-size:20px;font-weight:bold;color:#00c853;">${r['one_way_min']}</div>
          </td>
          <td style="padding:14px 10px;text-align:center;">
            <div style="font-size:14px;color:#3d5a7a;">${r['one_way_max']}</div>
          </td>
          <td style="padding:14px 10px;text-align:center;">
            <span style="background:{deal_color(r['deal_score'])}22;color:{deal_color(r['deal_score'])};padding:4px 10px;border-radius:12px;font-size:12px;font-weight:bold;">{r['deal_score']}/10</span>
          </td>
          <td style="padding:14px 10px;color:#7eb8f7;font-size:12px;">{trend_arrow(r.get('price_trend','stable'))}</td>
          <td style="padding:14px 10px;color:#5a7a9a;font-size:11px;">May 10–20</td>
        </tr>
        <tr style="border-bottom:2px solid #0d1929;background:#070d18;">
          <td colspan="6" style="padding:6px 10px 12px 10px;color:#5a7a9a;font-size:11px;font-style:italic;">
            ✈ {r['recommended_airlines'][0] if r.get('recommended_airlines') else 'Check airlines'} &nbsp;|&nbsp; 💡 {r.get('tip','')}
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>body{{margin:0;padding:0;background:#050b14;font-family:'Courier New',monospace;color:#cdd9e8;}}</style>
</head>
<body>
<div style="max-width:700px;margin:0 auto;padding:24px;">
  <div style="text-align:center;padding:30px 0 20px;border-bottom:1px solid #1a2a3a;margin-bottom:24px;">
    <div style="font-size:11px;letter-spacing:5px;color:#4488ff;margin-bottom:8px;">AI FLIGHT AGENT • DAILY REPORT</div>
    <h1 style="margin:0;font-size:28px;font-weight:900;color:#4488ff;">✈ FLIGHT PRICE HUNTER</h1>
    <div style="color:#3d5a7a;font-size:13px;margin-top:8px;">BLR → Los Angeles · San Francisco · Dallas · Houston · New York · Little Rock | Sep–Dec 2026</div>
    <div style="color:#3d5a7a;font-size:11px;margin-top:4px;">Report generated: {now_cst}</div>
  </div>
  {prime_banner}
  <div style="background:linear-gradient(135deg,#0a1f0a,#081528);border:1px solid #00c85333;border-radius:12px;padding:20px;margin-bottom:20px;text-align:center;">
    <div style="font-size:11px;letter-spacing:3px;color:#00c853;margin-bottom:8px;">🏆 TODAY'S BEST DEAL</div>
    <div style="font-size:24px;font-weight:bold;color:white;">BLR → {cheapest['city']}, {cheapest['state']}</div>
    <div style="font-size:28px;font-weight:bold;color:#00c853;margin:8px 0;">From ${cheapest['round_trip_min']} round-trip</div>
    <div style="color:#5a8a5a;font-size:13px;">Best window: {data.get('best_travel_window','September–December 2026')}</div>
    {"<div style='background:#0a1a0a;border:1px solid #00c85344;border-radius:8px;padding:10px;margin-top:12px;color:#7acc7a;font-size:13px;'>⚡ " + data.get('price_alert','') + "</div>" if data.get('price_alert') else ''}
  </div>
  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:12px;overflow:hidden;margin-bottom:20px;">
    <div style="padding:14px 16px;border-bottom:1px solid #1a2a3a;font-size:11px;letter-spacing:3px;color:#4488ff;">📊 ALL ROUTES ANALYZED</div>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="background:#0a1220;font-size:10px;letter-spacing:1px;color:#3d5a7a;text-transform:uppercase;">
          <th style="padding:10px;text-align:left;">Destination</th>
          <th style="padding:10px;text-align:center;">One-Way</th>
          <th style="padding:10px;text-align:center;">Round-Trip</th>
          <th style="padding:10px;text-align:center;">Deal Score</th>
          <th style="padding:10px;text-align:center;">Trend</th>
          <th style="padding:10px;text-align:left;">Best Month</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:12px;padding:18px;margin-bottom:20px;">
    <div style="font-size:11px;letter-spacing:3px;color:#4488ff;margin-bottom:14px;">💡 AI BOOKING TIPS</div>
    {tips_html}
  </div>
  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:12px;padding:18px;margin-bottom:20px;">
    <div style="font-size:11px;letter-spacing:3px;color:#4488ff;margin-bottom:10px;">📝 SUMMARY</div>
    <div style="color:#8aaccc;font-size:13px;line-height:1.7;">{data.get('summary','')}</div>
  </div>
  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:12px;padding:18px;margin-bottom:20px;">
    <div style="font-size:11px;letter-spacing:3px;color:#4488ff;margin-bottom:14px;">🔗 BOOK NOW</div>
    <a href="https://www.google.com/flights" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🔍 Google Flights</a>
    <a href="https://www.skyscanner.co.in" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🛫 Skyscanner</a>
    <a href="https://www.kayak.co.in" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">📊 Kayak</a>
    <a href="https://www.makemytrip.com/flights/international" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🇮🇳 MakeMyTrip</a>
  </div>
  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:12px;overflow:hidden;margin-bottom:20px;">
    <div style="padding:14px 16px;border-bottom:1px solid #1a2a3a;font-size:11px;letter-spacing:3px;color:#ffab00;">🇺🇸 DOMESTIC ROUTES — LIT ↔ SFO</div>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="background:#0a1220;font-size:10px;letter-spacing:1px;color:#3d5a7a;text-transform:uppercase;">
          <th style="padding:10px;text-align:left;">Route</th>
          <th style="padding:10px;text-align:center;">One-Way From</th>
          <th style="padding:10px;text-align:center;">One-Way Max</th>
          <th style="padding:10px;text-align:center;">Deal Score</th>
          <th style="padding:10px;text-align:center;">Trend</th>
          <th style="padding:10px;text-align:left;">Best Month</th>
        </tr>
      </thead>
      <tbody>{domestic_rows}</tbody>
    </table>
  </div>
  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:12px;padding:14px 16px;margin-bottom:20px;font-size:13px;color:#8aaccc;">
    <div style="font-size:11px;letter-spacing:3px;color:#ffab00;margin-bottom:10px;">📝 DOMESTIC SUMMARY</div>
    {domestic_summary}
  </div>
  <div style="text-align:center;color:#1e2a3a;font-size:10px;letter-spacing:2px;padding-top:16px;border-top:1px solid #0d1520;">
    AI FLIGHT AGENT • DAILY SCAN • PRICES ARE AI ESTIMATES — VERIFY BEFORE BOOKING
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
    log.info(f"📧 Email sent to {RECIPIENT_EMAIL} — ID: {response['id']}")


# ─────────────────────────────────────────────
#  🎯 MAIN JOB
# ─────────────────────────────────────────────
def flight_check_job():
    now_cst    = datetime.now(CST)
    weekday    = now_cst.weekday()       # 0=Mon, 1=Tue, 2=Wed
    is_tue_wed = weekday in (1, 2)
    day_name   = now_cst.strftime("%A")

    log.info(f"🚀 Starting flight check — {day_name} {'⭐ PRIME DAY' if is_tue_wed else ''}")

    try:
        data = research_flights(is_tue_wed)
        domestic_data = research_domestic_flights()

        cheapest_dest  = data.get("overall_cheapest", "?")
        cheapest_route = next((r for r in data["routes"] if r["destination"] == cheapest_dest), data["routes"][0])
        price          = cheapest_route.get("round_trip_min", "?")

        prime_tag = " ⭐ PRIME BOOKING DAY" if is_tue_wed else ""
        subject = (
            f"✈️ BLR→USA + LIT↔SFO Flight Alert: {cheapest_dest} from ${price} RT "
            f"| {day_name}{prime_tag} | {now_cst.strftime('%b %d')}"
        )

        html = build_html_email(data, is_tue_wed, domestic_data)
        send_email(html, subject)
        log.info("✅ Job completed successfully.")

    except Exception as e:
        log.error(f"❌ Job failed: {e}", exc_info=True)


# ─────────────────────────────────────────────
#  ⏰ SCHEDULER — runs at 2:30 AM CST daily
# ─────────────────────────────────────────────
def run_scheduler():
    log.info("=" * 55)
    log.info("  ✈️  BLR → USA FLIGHT TRACKER AGENT STARTED")
    log.info("  📅  Daily run: 2:30 AM CST")
    log.info("  ⭐  Extra focus on Tuesdays & Wednesdays")
    log.info(f"  📧  Sending to: {RECIPIENT_EMAIL}")
    log.info("=" * 55)

    # Schedule daily at 2:30 AM CST
    schedule.every().day.at("02:30").do(flight_check_job)

    # Run immediately on startup as a test
    log.info("🧪 Running initial test job now...")
    flight_check_job()

    log.info("⏰ Scheduler active. Waiting for 2:30 AM CST each night...")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run_scheduler()
