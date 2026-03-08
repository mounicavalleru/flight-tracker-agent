# ✈️ BLR → USA Flight Price Hunter

An automated AI-powered flight tracking agent that monitors and reports the cheapest flights from Bangalore (BLR) to major US cities daily.

## 🚀 Live Demo
Deployed and running 24/7 on [Railway](https://railway.app)

## 📌 What It Does
- Runs automatically every day at **2:30 AM CST**
- Uses **Groq AI (LLaMA 3.3)** to research and analyze flight prices
- Tracks 6 routes: BLR → LAX, SFO, DFW, IAH, JFK, LIT
- Sends a beautifully formatted **HTML email report** with:
  - One-way vs round-trip price comparisons
  - Deal scores and price trends
  - Airline recommendations and best layovers
  - Best travel windows (September–December 2026)
- Highlights **Tuesday/Wednesday** as prime booking days

## 🛠️ Tech Stack
| Tool | Purpose |
|---|---|
| Python 3.13 | Core language |
| Groq API (LLaMA 3.3 70B) | AI flight research |
| Resend API | Email delivery |
| Railway | Cloud deployment & scheduling |
| GitHub | Version control & CI/CD |

## 📊 Architecture
```
GitHub (code) → Railway (scheduler)
                    ↓ runs daily at 2:30 AM
              Groq AI API (research flights)
                    ↓
              Resend API (send HTML email)
                    ↓
              mounicachowdry@gmail.com
```

## ⚙️ Environment Variables
Set these in Railway (never hardcode):
```
GROQ_API_KEY       # Groq AI API key
RESEND_API_KEY     # Resend email API key
SENDER_EMAIL       # Verified sender email address
RECIPIENT_EMAIL    # Recipient email address
```

## 📦 Installation & Local Setup
```bash
# Clone the repo
git clone https://github.com/mounicavalleru/flight-tracker-agent.git
cd flight-tracker-agent

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GROQ_API_KEY=your_key_here
export RESEND_API_KEY=your_key_here
export SENDER_EMAIL=onboarding@resend.dev
export RECIPIENT_EMAIL=recipient@gmail.com

# Run
python flight_tracker_agent_v2.py
```

## 📧 Sample Email Report
The agent sends a dark-themed HTML email including:
- 🏆 Best deal highlight
- 📊 Full route comparison table with deal scores
- 📉 Price trend indicators
- 💡 AI-generated booking tips
- 🔗 Direct links to Google Flights, Skyscanner, Kayak, MakeMyTrip

## 🔄 CI/CD Pipeline
- Push to `main` branch → Railway auto-deploys
- Zero-downtime deployments
- Logs available in Railway dashboard

## 📝 Key Learnings
- Building and deploying autonomous AI agents
- Integrating LLM APIs (Groq/LLaMA) for structured JSON output
- Automated email delivery with Resend API
- Cloud deployment and scheduling with Railway
- Environment variable management and security best practices

## 💼 Product Management Relevance
- **Problem → Solution thinking**: Identified a real personal pain point (tracking cheap BLR→USA flights) and built a fully automated solution end-to-end — mirrors core PM skill of owning a problem and shipping a solution
- **Data-driven decisions**: Designed AI output as structured data with deal scores, price trends, and booking tips — demonstrates how to present data to drive user action
- **Tradeoffs under constraints**: Evaluated and switched between multiple providers (Anthropic → Gemini → Groq, Gmail → SendGrid → Resend) based on cost, reliability, and free tier limits — reflects real PM decision-making
- **Full product lifecycle ownership**: Handled ideation, scoping, building, deploying, debugging in production, and iterating — shows the accountability and ownership mindset expected of a PM
- **Scalability thinking**: Built with CI/CD, environment variables, and modular code so new routes or features can be added easily — demonstrates systems thinking and planning ahead

## 👩‍💻 Author
**Mounica Chowdry** — [GitHub](https://github.com/mounicavalleru)
