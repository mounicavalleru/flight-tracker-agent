#!/usr/bin/env python3
"""
✈️  BLR → USA Flight Price Hunter — 24/7 Tracker
Checks prices every hour via GitHub Actions
Sends morning email with current prices
Sends INSTANT alert email whenever a new lowest price is found
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

CST        = pytz.timezone("America/Chicago")
STATE_FILE = "daily_lowest_prices.json"

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
#  💾 STATE — track lowest prices found today
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


def update_lowest_prices(state: dict, today: str, new_data: dict, new_domestic: dict) -> dict:
    """
    Compare new prices with stored lowest prices for today.
    Keep the lowest price found for each route across all hourly checks.
    """
    if state.get("date") != today:
        # New day — reset everything
        log.info(f"📅 New day ({today}) — resetting price tracking")
        state = {"date": today, "routes": {}, "domestic": {}, "email_sent": False, "checks": 0}

    state["checks"] = state.get("checks", 0) + 1

    # Update international routes
    for r in new_data.get("routes", []):
        code = r["destination"]
        stored = state["routes"].get(code, {})
        # Keep the lowest round_trip_min found today
        if not stored or r["round_trip_min"] < stored.get("round_trip_min", 9999):
            state["routes"][code] = r
            log.info(f"📉 New low for {code}: ${r['round_trip_min']} RT")
        else:
            log.info(f"ℹ️  {code}: ${r['round_trip_min']} RT (current best: ${stored['round_trip_min']})")

    # Update overall cheapest
    if state["routes"]:
        cheapest_code = min(state["routes"], key=lambda c: state["routes"][c].get("round_trip_min", 9999))
        state["overall_cheapest"] = cheapest_code
        state["best_travel_window"] = new_data.get("best_travel_window", "Sep–Dec 2026")
        state["summary"] = new_data.get("summary", "")
        state["booking_tips"] = new_data.get("booking_tips", [])
        state["price_alert"] = new_data.get("price_alert", "")

    # Update domestic routes
    for r in new_domestic.get("domestic_routes", []):
        key = f"{r['from_code']}-{r['to_code']}"
        stored = state["domestic"].get(key, {})
        if not stored or r["one_way_min"] < stored.get("one_way_min", 9999):
            state["domestic"][key] = r
            log.info(f"📉 New low for {key}: ${r['one_way_min']}")
    state["domestic_summary"] = new_domestic.get("domestic_summary", "")

    return state


# ─────────────────────────────────────────────
#  🤖 AI RESEARCH
# ─────────────────────────────────────────────
def research_flights(is_tue_wed: bool) -> dict:
    log.info("🤖 Starting AI flight research with Groq...")

    focus_note = (
        "IMPORTANT: Today is Tuesday or Wednesday — historically the CHEAPEST days to book. "
        "Highlight any extra savings available for booking TODAY."
        if is_tue_wed else
        "Note: Tuesday and Wednesday tend to have cheapest fares — flag if deals should wait."
    )

    prompt = f"""Research flight prices from Bangalore (BLR) to these US destinations for September-December 2026:
Los Angeles (LAX), San Francisco (SFO), Dallas (DFW), Houston (IAH), New York (JFK), Little Rock (LIT).

{focus_note}

Compare one-way vs round-trip. Find absolute cheapest options.
Today's date: {datetime.now(CST).strftime('%A, %B %d, %Y')}.

Respond with ONLY valid JSON (no markdown, no backticks):
{{
  "routes": [
    {{
      "destination": "LAX",
      "city": "Los Angeles",
      "state": "California",
      "one_way_min": 650,
      "one_way_max": 950,
      "round_trip_min": 900,
      "round_trip_max": 1400,
      "best_months": ["September", "October"],
      "cheapest_option": "round_trip",
      "recommended_airlines": ["Air India", "Emirates"],
      "best_layover": "Dubai",
      "deal_score": 7,
      "price_trend": "dropping",
      "tip": "Book now - prices rising after March"
    }}
  ],
  "overall_cheapest": "LAX",
  "best_travel_window": "September 1-15 or Dec 5-20",
  "price_alert": "Notable deals worth highlighting",
  "summary": "2-3 sentence summary",
  "booking_tips": ["tip1", "tip2", "tip3"]
}}"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    data = json.loads(raw.strip())
    log.info(f"✅ Research complete. Cheapest: {data.get('overall_cheapest')}")
    return data


def research_domestic_flights() -> dict:
    log.info("🤖 Starting domestic flight research (LIT ↔ SFO)...")
    prompt = f"""Research domestic US flight prices SPECIFICALLY for May 10-20, 2026 for:
1. Little Rock (LIT) → San Francisco (SFO)
2. San Francisco (SFO) → Little Rock (LIT)

IMPORTANT: Use ONLY May in best_months. Do NOT suggest other months.
Today: {datetime.now(CST).strftime('%A, %B %d, %Y')}.

Respond ONLY with valid JSON:
{{
  "domestic_routes": [
    {{
      "from_code": "LIT", "from_city": "Little Rock",
      "to_code": "SFO", "to_city": "San Francisco",
      "one_way_min": 200, "one_way_max": 450,
      "best_months": ["May"],
      "recommended_airlines": ["American Airlines", "United"],
      "deal_score": 7, "price_trend": "stable",
      "tip": "Book 3-4 weeks ahead"
    }},
    {{
      "from_code": "SFO", "from_city": "San Francisco",
      "to_code": "LIT", "to_city": "Little Rock",
      "one_way_min": 200, "one_way_max": 450,
      "best_months": ["May"],
      "recommended_airlines": ["American Airlines", "United"],
      "deal_score": 7, "price_trend": "stable",
      "tip": "Tue/Wed departures cheapest"
    }}
  ],
  "domestic_summary": "Brief summary"
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
def build_html_email(state: dict, is_tue_wed: bool, checks: int) -> str:
    now_cst  = datetime.now(CST).strftime("%A, %B %d, %Y at %I:%M %p CST")
    routes   = list(state["routes"].values())
    cheapest = state["routes"].get(state.get("overall_cheapest", ""), routes[0] if routes else {})

    def deal_color(score):
        if score >= 8: return "#00c853"
        if score >= 6: return "#ffab00"
        return "#ff5252"

    def trend_arrow(trend):
        return {"dropping": "📉 Dropping", "rising": "📈 Rising", "stable": "➡️ Stable"}.get(trend, "➡️ Stable")

    rows = ""
    for r in sorted(routes, key=lambda x: x.get("round_trip_min", 9999)):
        dest  = next((d for d in ROUTES if d["code"] == r["destination"]), {})
        emoji = dest.get("emoji", "✈️")
        badge = "🏆 BEST DEAL" if r["destination"] == state.get("overall_cheapest") else ""
        rows += f"""
        <tr style="border-bottom:1px solid #1e2a3a;">
          <td style="padding:14px 10px;color:#7eb8f7;font-weight:bold;">
            {emoji} {r['city']}<br>
            <span style="font-size:11px;color:#3d5a7a;">{r['state']} • {r['destination']}</span>
            {"<br><span style='font-size:11px;background:#1a3a1a;color:#00c853;padding:2px 6px;border-radius:4px;'>" + badge + "</span>" if badge else ""}
          </td>
          <td style="padding:14px 10px;text-align:center;">
            <div style="font-size:20px;font-weight:bold;color:{'#00c853' if r.get('cheapest_option')=='one_way' else '#ccc'};">${r['one_way_min']}</div>
            <div style="font-size:11px;color:#3d5a7a;">up to ${r['one_way_max']}</div>
          </td>
          <td style="padding:14px 10px;text-align:center;">
            <div style="font-size:20px;font-weight:bold;color:{'#00c853' if r.get('cheapest_option')=='round_trip' else '#ccc'};">${r['round_trip_min']}</div>
            <div style="font-size:11px;color:#3d5a7a;">up to ${r['round_trip_max']}</div>
            {"<div style='font-size:10px;color:#00c853;'>✅ CHEAPEST TODAY</div>" if badge else ""}
          </td>
          <td style="padding:14px 10px;text-align:center;">
            <span style="background:{deal_color(r['deal_score'])}22;color:{deal_color(r['deal_score'])};padding:4px 10px;border-radius:12px;font-size:12px;font-weight:bold;">{r['deal_score']}/10</span>
          </td>
          <td style="padding:14px 10px;color:#7eb8f7;font-size:12px;">{trend_arrow(r.get('price_trend','stable'))}</td>
          <td style="padding:14px 10px;color:#5a7a9a;font-size:11px;">{', '.join(r.get('best_months', ['Sep'])[:2])}</td>
        </tr>
        <tr style="border-bottom:2px solid #0d1929;background:#070d18;">
          <td colspan="6" style="padding:6px 10px 12px;color:#5a7a9a;font-size:11px;font-style:italic;">
            ✈ {r['recommended_airlines'][0] if r.get('recommended_airlines') else 'Check airlines'} via {r.get('best_layover','—')} &nbsp;|&nbsp; 💡 {r.get('tip','')}
          </td>
        </tr>"""

    tips_html = "".join([
        f'<div style="display:flex;gap:10px;margin-bottom:10px;font-size:13px;color:#8aaccc;"><span style="color:#1e6eff;min-width:22px;font-weight:bold;">{i+1}.</span><span>{tip}</span></div>'
        for i, tip in enumerate(state.get("booking_tips", []))
    ])

    prime_banner = ""
    if is_tue_wed:
        prime_banner = """
        <div style="background:linear-gradient(135deg,#0d2a0d,#0a1f0a);border:1px solid #00c85344;border-radius:10px;padding:16px;margin-bottom:20px;text-align:center;">
          <div style="font-size:11px;letter-spacing:3px;color:#00c853;margin-bottom:6px;">⚡ PRIME BOOKING DAY</div>
          <div style="font-size:15px;color:white;font-weight:bold;">Today is Tue/Wed — Airlines post lowest fares today!</div>
        </div>"""

    domestic_rows = ""
    for r in state.get("domestic", {}).values():
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
          <td colspan="6" style="padding:6px 10px 12px;color:#5a7a9a;font-size:11px;font-style:italic;">
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
    <div style="font-size:11px;letter-spacing:5px;color:#4488ff;margin-bottom:8px;">AI FLIGHT AGENT • DAILY BEST PRICES REPORT</div>
    <h1 style="margin:0;font-size:28px;font-weight:900;color:#4488ff;">✈ FLIGHT PRICE HUNTER</h1>
    <div style="color:#3d5a7a;font-size:13px;margin-top:8px;">BLR → LAX · SFO · DFW · IAH · JFK · LIT | Sep–Dec 2026</div>
    <div style="color:#3d5a7a;font-size:11px;margin-top:4px;">Report generated: {now_cst}</div>
    <div style="background:#0a1f3a;border:1px solid #1a3a5a;border-radius:8px;padding:10px;margin-top:14px;display:inline-block;">
      <span style="color:#4488ff;font-size:13px;">📊 Based on <strong style="color:white;">{checks} price checks</strong> done today — showing LOWEST prices found</span>
    </div>
  </div>
  {prime_banner}
  <div style="background:linear-gradient(135deg,#0a1f0a,#081528);border:1px solid #00c85333;border-radius:12px;padding:20px;margin-bottom:20px;text-align:center;">
    <div style="font-size:11px;letter-spacing:3px;color:#00c853;margin-bottom:8px;">🏆 TODAY'S BEST DEAL</div>
    <div style="font-size:24px;font-weight:bold;color:white;">BLR → {cheapest.get('city','')}, {cheapest.get('state','')}</div>
    <div style="font-size:32px;font-weight:bold;color:#00c853;margin:8px 0;">From ${cheapest.get('round_trip_min','?')} round-trip</div>
    <div style="color:#5a8a5a;font-size:13px;">Best window: {state.get('best_travel_window','Sep–Dec 2026')}</div>
    {"<div style='background:#0a1a0a;border:1px solid #00c85344;border-radius:8px;padding:10px;margin-top:12px;color:#7acc7a;font-size:13px;'>⚡ " + state.get('price_alert','') + "</div>" if state.get('price_alert') else ''}
  </div>
  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:12px;overflow:hidden;margin-bottom:20px;">
    <div style="padding:14px 16px;border-bottom:1px solid #1a2a3a;font-size:11px;letter-spacing:3px;color:#4488ff;">📊 ALL ROUTES — LOWEST PRICES TODAY</div>
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
    <div style="color:#8aaccc;font-size:13px;line-height:1.7;">{state.get('summary','')}</div>
  </div>
  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:12px;padding:18px;margin-bottom:20px;">
    <div style="font-size:11px;letter-spacing:3px;color:#4488ff;margin-bottom:14px;">🔗 BOOK NOW</div>
    <a href="https://www.google.com/flights" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🔍 Google Flights</a>
    <a href="https://www.skyscanner.co.in" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🛫 Skyscanner</a>
    <a href="https://www.kayak.co.in" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">📊 Kayak</a>
    <a href="https://www.makemytrip.com/flights/international" style="background:#1a2a4a;border:1px solid #2a3a5a;padding:10px 16px;border-radius:8px;color:#7eb8f7;font-size:12px;text-decoration:none;display:inline-block;margin:4px;">🇮🇳 MakeMyTrip</a>
  </div>
  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:12px;overflow:hidden;margin-bottom:20px;">
    <div style="padding:14px 16px;border-bottom:1px solid #1a2a3a;font-size:11px;letter-spacing:3px;color:#ffab00;">🇺🇸 DOMESTIC — LIT ↔ SFO (May 10–20)</div>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="background:#0a1220;font-size:10px;letter-spacing:1px;color:#3d5a7a;text-transform:uppercase;">
          <th style="padding:10px;text-align:left;">Route</th>
          <th style="padding:10px;text-align:center;">One-Way From</th>
          <th style="padding:10px;text-align:center;">One-Way Max</th>
          <th style="padding:10px;text-align:center;">Deal Score</th>
          <th style="padding:10px;text-align:center;">Trend</th>
          <th style="padding:10px;text-align:left;">Travel Dates</th>
        </tr>
      </thead>
      <tbody>{domestic_rows}</tbody>
    </table>
  </div>
  <div style="background:#070d18;border:1px solid #1a2a3a;border-radius:12px;padding:14px 16px;margin-bottom:20px;font-size:13px;color:#8aaccc;">
    <div style="font-size:11px;letter-spacing:3px;color:#ffab00;margin-bottom:10px;">📝 DOMESTIC SUMMARY</div>
    {state.get('domestic_summary','')}
  </div>
  <div style="text-align:center;color:#1e2a3a;font-size:10px;letter-spacing:2px;padding-top:16px;border-top:1px solid #0d1520;">
    AI FLIGHT AGENT • DAILY BEST PRICES • VERIFY BEFORE BOOKING
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
    now        = datetime.now(CST)
    today      = now.strftime("%Y-%m-%d")
    weekday    = now.weekday()
    is_tue_wed = weekday in (1, 2)
    now_str    = now.strftime("%A, %B %d at %I:%M %p CST")

    log.info("=" * 55)
    log.info("  ✈️  BLR → USA FLIGHT TRACKER — HOURLY CHECK")
    log.info(f"  🕐  Time: {now_str}")
    log.info(f"  📧  Sending to: {RECIPIENT_EMAIL}")
    log.info("=" * 55)

    # Load today's stored lowest prices
    state = load_state()

    # Remember previous best price before this check
    prev_cheapest_code  = state.get("overall_cheapest", "")
    prev_cheapest_route = state.get("routes", {}).get(prev_cheapest_code, {})
    prev_best_price     = prev_cheapest_route.get("round_trip_min", 9999)

    # Fetch new prices
    log.info("🔍 Fetching current prices...")
    new_data     = research_flights(is_tue_wed)
    new_domestic = research_domestic_flights()

    # Update state with lowest prices found
    state = update_lowest_prices(state, today, new_data, new_domestic)
    save_state(state)

    checks = state.get("checks", 1)
    log.info(f"✅ Price check #{checks} complete for today")

    # Get new best price after this check
    new_cheapest_code  = state.get("overall_cheapest", "")
    new_cheapest_route = state["routes"].get(new_cheapest_code, {})
    new_best_price     = new_cheapest_route.get("round_trip_min", 9999)

    # ── SFO PRICE ALERT — send immediately if SFO RT drops to $200 or less ──
    SFO_ALERT_THRESHOLD = 200
    sfo_route    = state["routes"].get("SFO", {})
    sfo_rt_price = sfo_route.get("round_trip_min", 9999)
    sfo_alerted  = state.get("sfo_alert_sent_date") == today

    if sfo_rt_price <= SFO_ALERT_THRESHOLD and not sfo_alerted:
        log.info(f"🚨 SFO PRICE ALERT! RT dropped to ${sfo_rt_price} — under $200 threshold!")
        prime_tag = " ⭐ PRIME DAY" if is_tue_wed else ""
        subject = (
            f"🚨 SFO ALERT: BLR→San Francisco dropped to ${sfo_rt_price} RT! "
            f"| {now.strftime('%b %d %I:%M %p')}{prime_tag}"
        )
        html = build_html_email(state, is_tue_wed, checks)
        send_email(html, subject)
        state["sfo_alert_sent_date"] = today
        save_state(state)
        log.info("✅ SFO price alert email sent!")

    elif sfo_rt_price <= SFO_ALERT_THRESHOLD and sfo_alerted:
        log.info(f"📵 SFO alert already sent today (${sfo_rt_price} RT) — skipping")

    # ── GENERAL NEW LOW ALERT ──
    elif new_best_price < prev_best_price:
        drop = prev_best_price - new_best_price
        log.info(f"🎉 NEW LOWEST PRICE! ${prev_best_price} → ${new_best_price} (saved ${drop})")
        prime_tag = " ⭐ PRIME DAY" if is_tue_wed else ""
        subject = (
            f"🔥 NEW LOW: BLR→{new_cheapest_code} dropped to ${new_best_price} RT! "
            f"(Saved ${drop}) | {now.strftime('%b %d %I:%M %p')}{prime_tag}"
        )
        html = build_html_email(state, is_tue_wed, checks)
        send_email(html, subject)
        log.info("✅ Instant alert email sent!")

    elif checks == 1:
        log.info("🌅 First check of the day — sending morning prices email")
        prime_tag = " ⭐ PRIME DAY" if is_tue_wed else ""
        subject = (
            f"✈️ Morning Prices: BLR→{new_cheapest_code} from ${new_best_price} RT | "
            f"{now.strftime('%b %d')}{prime_tag}"
        )
        html = build_html_email(state, is_tue_wed, checks)
        send_email(html, subject)
        log.info("✅ Morning email sent!")

    else:
        log.info(f"ℹ️  No alerts. SFO RT: ${sfo_rt_price} | Best: BLR→{new_cheapest_code} ${new_best_price} RT")

    log.info("✅ Done!")


if __name__ == "__main__":
    main()
