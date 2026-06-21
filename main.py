import os
import json
import asyncio
from fastapi import FastAPI, Request, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI
from tavily import TavilyClient
import praw
from dotenv import load_dotenv
import base64

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")
# ==========================================
# 1. INITIALIZE CLIENTS (Used by both tools)
# ==========================================
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent="MarketScope_v1_by_your_name" 
)

# ==========================================
# TOOL 1: THE MARKET ESTIMATOR (TAM/SAM/SOM)
# ==========================================
class AdvancedRequest(BaseModel):
    idea: str
    country: str
    methodology: str
    price: float = 0
    frequency: float = 1

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/analyze")
async def analyze_market(data: AdvancedRequest):
    print(f"--- Starting Analysis: {data.methodology} ---")
    thinking_log = []

    try:
        # 1. TAVILY SEARCH STRATEGY
        market_query_prompt = f"Find total number of potential customers for '{data.idea}' in {data.country} and Globally. Do NOT look for revenue." if data.methodology == "bottom-up" else f"Find current market size USD, CAGR for '{data.idea}' in {data.country} and Globally."

        thinking_log.append("🔍 Executing Tavily Web Searches...")
        market_search = tavily.search(query=market_query_prompt, search_depth="advanced")
        comp_search = tavily.search(query=f"Top startup competitors for: {data.idea}", search_depth="advanced")
        ip_search = tavily.search(query=f"site:patents.google.com OR site:arxiv.org \"{data.idea}\"", search_depth="advanced")

        # 2. REDDIT SENTIMENT SEARCH (SEGMENTED)
        thinking_log.append("👽 Scraping targeted subreddits for sentiment segmentation...")
        reddit_content = ""
        
        target_subs = ["SaaS", "Entrepreneur", "startups", "technology"]
        
        for sub in target_subs:
            thinking_log.append(f"   ↳ Scraping r/{sub}...")
            try:
                search_results = reddit.subreddit(sub).search(data.idea, limit=3)
                posts_found = False
                
                reddit_content += f"\n--- SUBREDDIT: r/{sub} ---\n"
                for post in search_results:
                    posts_found = True
                    reddit_content += f"Score: {post.score} | Text: {post.title} - {post.selftext[:150]}...\n"
                
                if not posts_found:
                    reddit_content += "No recent discussions found.\n"
                    
            except Exception as e:
                reddit_content += f"Could not access r/{sub}.\n"

        thinking_log.append("✓ Reddit segmentation complete.")

        # 3. COMBINE ALL CONTEXT
        full_context = f"""
        MARKET DATA: {market_search['results']}
        COMPETITORS: {comp_search['results']}
        PATENTS/RESEARCH: {ip_search['results']}
        REDDIT DISCUSSIONS: {reddit_content}
        """

        # 4. GPT-4o SYNTHESIS 
        thinking_log.append("🧠 Scoring sentiment and synthesizing report...")
        
        system_prompt = f"""
        You are a Senior VC Associate and Product Analyst. Generate a structured market report.
        METHODOLOGY: {data.methodology.upper()}
        USER INPUTS: Price=${data.price}, Freq={data.frequency}/yr.
        
        RULES FOR REDDIT SENTIMENT:
        Analyze the 'REDDIT DISCUSSIONS' block. For each subreddit provided, assign a sentiment score from 0 to 100.
        (0 = Highly toxic/dismissive, 50 = Neutral/No data, 100 = Highly enthusiastic/validated).
        
        OUTPUT JSON FORMAT:
        {{
            "tam": "string ($X B)", "sam": "string ($X M)", "som": "string ($X M)", "cagr": "string (X%)",
            "competitors": [{{"name": "string", "description": "string"}}],
            "patents": [{{"title": "string", "url": "string"}}],
            "reddit_breakdown": [
                {{
                    "subreddit": "string (e.g., r/SaaS)", 
                    "score": int, 
                    "vibe": "string (Bullish, Bearish, or Neutral)", 
                    "summary": "string"
                }}
            ],
            "thinking": "string"
        }}
        """

        ai_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context: {full_context}\n\nIdea: {data.idea}"}
            ],
            response_format={"type": "json_object"}
        )

        result = json.loads(ai_response.choices[0].message.content)
        result["thinking"] = "\n".join(thinking_log) + "\n\n-- AI REASONING --\n" + result["thinking"]

        return result

    except Exception as e:
        print(f"Error: {e}")
        return {"error": str(e)}


# ==========================================
# TOOL 2: THE VC SIMULATOR (CHATBOT)
# ==========================================

# Helper function to load our JSON Database
def load_founders_db():
    with open("founders_db.json", "r") as file:
        return json.load(file)

def build_system_prompt(founder_id: str):
    db = load_founders_db()
    scenario = db.get(founder_id)
    
    if not scenario:
        raise ValueError("Founder ID not found in database.")

    # Convert the nested JSON objects into readable text strings for the AI
    public_info = json.dumps(scenario.get('public_data', {}), indent=2)
    diligence_info = json.dumps(scenario.get('deep_diligence_data', {}), indent=2)
    secrets_info = json.dumps(scenario.get('hidden_secrets', {}), indent=2)

    return f"""
    You are {scenario['founder_name']}, the founder of {scenario['company_name']}.
    You are in a pitch meeting with a Venture Capital Analyst.
    
    YOUR PERSONALITY:
    {scenario['persona']}
    
    BEHAVIORAL TRIGGERS:
    {scenario['triggers']}
    
    YOUR PUBLIC METRICS (Share freely):
    {public_info}
    
    DEEP DILIGENCE DATA (Share confidently if asked specific technical/GTM questions):
    {diligence_info}
    
    YOUR SECRETS (DO NOT REVEAL UNLESS THE VC PRESSES YOU ON THESE EXACT VULNERABILITIES):
    {secrets_info}
    
    RULES:
    1. Speak entirely in the first person as the founder.
    2. Keep responses conversational and brief (2-4 sentences). Do not monologue.
    3. NEVER break character. Never admit you are an AI.
    4. Guard your secrets fiercely unless the VC specifically figures out the flaw.
    """

# Updated Data model to accept the founder ID from the frontend
class ChatRequest(BaseModel):
    founder_id: str
    messages: list[dict]

# --- NEW ROUTE FOR THE DEBRIEF ENGINE ---

class DebriefRequest(BaseModel):
    founder_id: str
    history: list[dict]
    decision: str
    thesis: str

@app.post("/debrief")
async def generate_debrief(request: DebriefRequest):
    try:
        db = load_founders_db()
        scenario = db.get(request.founder_id)
        
        if not scenario:
            return {"error": "Founder not found"}

        # Extract the hidden lore the analyst was supposed to find
        secrets = json.dumps(scenario.get('hidden_secrets', {}), indent=2)
        
        # Format the chat history into a readable transcript
        transcript = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in request.history])
        
        system_prompt = f"""
        You are the Managing Partner at a top-tier Venture Capital firm. 
        Your Junior Analyst just completed a pitch meeting with {scenario['founder_name']} of {scenario['company_name']}.
        
        THE STARTUP'S ACTUAL REALITY (Hidden from the Analyst):
        {secrets}
        
        THE ANALYST'S DECISION: {request.decision.upper()}
        THE ANALYST'S THESIS: {request.thesis}
        
        INTERVIEW TRANSCRIPT:
        {transcript}
        
        YOUR JOB:
        Grade the analyst's performance. Be brutal but fair. 
        1. Did they uncover the hidden secrets/flaws?
        2. Did they ask the right follow-up questions?
        3. Is their thesis logically sound based on the transcript?
        
        OUTPUT JSON FORMAT:
        {{
            "score": int (0-100),
            "feedback_summary": "string (1-2 paragraphs of brutal, professional VC feedback on their performance)",
            "flaws_found": ["string (flaws they successfully uncovered)"],
            "flaws_missed": ["string (flaws they completely missed)"]
        }}
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_prompt}],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        
        return json.loads(response.choices[0].message.content)

    except Exception as e:
        print(f"Debrief Error: {e}")
        return {"error": str(e)}

@app.get("/simulator", response_class=HTMLResponse)
async def get_simulator(request: Request):
    return templates.TemplateResponse("simulator.html", {"request": request})

# New API Route so the frontend can fetch the list of available founders
@app.get("/api/founders")
async def get_founders():
    db = load_founders_db()
    # Return just the basic info for the frontend dropdown menu
    founders_list = []
    for f_id, f_data in db.items():
        founders_list.append({
            "id": f_id,
            "company": f_data["company_name"],
            "name": f_data["founder_name"]
        })
    return {"founders": founders_list}

@app.post("/chat")
async def chat_with_founder(request: ChatRequest):
    try:
        # Generate the prompt dynamically based on the requested founder
        system_prompt = build_system_prompt(request.founder_id)
        
        api_messages = [{"role": "system", "content": system_prompt}]
        api_messages.extend(request.messages)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=api_messages,
            temperature=0.7 
        )
        
        return {"reply": response.choices[0].message.content}

    except Exception as e:
        print(f"Chat Error: {e}")
        return {"error": str(e)}

# ==========================================
# TOOL 3: THE VOICE ENGINE (PHASE 3)
# ==========================================

# Assign specific OpenAI voices to specific founders for realism
VOICE_MAP = {
    "sim_001_ecofly": "echo",      # Elias (Male)
    "sim_002_glowgrid": "onyx",    # Chad (Male, energetic)
    "sim_003_sprintai": "shimmer",    # Sarah (Female)
    "sim_006_cardiosense": "onyx", # Dr. Aris (Male)
    "sim_007_helixgen": "shimmer"  # Dr. Maya (Female)
    # Any founder not listed here will default to "alloy"
}

# --- NEW ROUTES FOR PITCH PRESENTATION ---

@app.get("/api/founder/{founder_id}")
async def get_founder_data(founder_id: str):
    db = load_founders_db()
    founder = db.get(founder_id)
    if not founder:
        return {"error": "Founder not found"}
    return founder

class TTSRequest(BaseModel):
    text: str
    founder_id: str

@app.post("/generate-tts")
async def generate_tts(request: TTSRequest):
    try:
        voice_choice = VOICE_MAP.get(request.founder_id, "alloy")
        tts_response = client.audio.speech.create(
            model="tts-1",
            voice=voice_choice,
            input=request.text
        )
        audio_base64 = base64.b64encode(tts_response.content).decode('utf-8')
        return {"audio_base64": audio_base64}
    except Exception as e:
        return {"error": str(e)}

@app.post("/voice-chat")
async def voice_chat_with_founder(
    audio: UploadFile = File(...),
    founder_id: str = Form(...),
    messages: str = Form(...) # The frontend will send the history as a JSON string
):
    try:
        # 1. Save the uploaded audio temporarily
        temp_file_path = f"temp_{audio.filename}"
        with open(temp_file_path, "wb") as buffer:
            buffer.write(await audio.read())

        # 2. Transcribe with Whisper
        with open(temp_file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )
        user_text = transcript.text
        os.remove(temp_file_path) # Clean up the temp file

        # 3. Get AI Text Response
        history = json.loads(messages)
        system_prompt = build_system_prompt(founder_id)
        
        # Combine system prompt + history + the new transcribed user text
        api_messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": user_text}]

        chat_response = client.chat.completions.create(
            model="gpt-4o",
            messages=api_messages,
            temperature=0.7
        )
        ai_reply = chat_response.choices[0].message.content

        # 4. Convert AI Reply to Speech (TTS)
        voice_choice = VOICE_MAP.get(founder_id, "alloy")
        tts_response = client.audio.speech.create(
            model="tts-1",
            voice=voice_choice,
            input=ai_reply
        )
        
        # Convert the binary audio to base64 so we can send it in JSON
        audio_base64 = base64.b64encode(tts_response.content).decode('utf-8')

        return {
            "user_text": user_text,
            "reply": ai_reply,
            "audio_base64": audio_base64
        }

    except Exception as e:
        print(f"Voice Chat Error: {e}")
        return {"error": str(e)}