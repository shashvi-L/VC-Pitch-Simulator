# MarketScope AI

A hobby project built during my **Investor Analyst Fellowship at McMaster**. It combines a VC pitch simulator (primary focus) with an AI-powered market sizing tool.

## Features

- **VC Pitch Simulator** — Practice diligence with 13 AI founder personas. Watch a narrated pitch deck, run voice Q&A, submit Invest/Pass with a thesis, and receive a Managing Partner debrief.
- **Market Estimator** — Generate TAM/SAM/SOM reports with competitor, patent, and Reddit sentiment analysis.

## Setup

1. Clone the repo and create a virtual environment:

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and add your API keys:

```bash
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
```

Required keys: `OPENAI_API_KEY`, `TAVILY_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`

3. Run the app:

```bash
uvicorn main:app --reload
```

4. Open in your browser:

- Market Estimator: http://127.0.0.1:8000/
- VC Pitch Simulator: http://127.0.0.1:8000/simulator

## Notes

- The simulator Q&A uses your microphone (browser permission required).
- Only the SprintAI founder has a full narrated pitch deck; other scenarios focus on Q&A.
