import os
import requests
import feedparser
import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import logging
import uuid
import io
from pydub import AudioSegment
import shutil

# Configure FFmpeg - to find it automatically
def setup_ffmpeg():
    """Automatically detect and configure FFmpeg path"""
    # Common FFmpeg locations on Windows
    possible_paths = [
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
        "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
        "C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe",
        "ffmpeg.exe"  
    ]
    
    for path in possible_paths:
        if shutil.which(path) or os.path.exists(path):
            AudioSegment.converter = path
            logger.info(f"FFmpeg found at: {path}")
            return True
    
    # Try using ffmpeg from PATH (common on Linux/Mac)
    if shutil.which("ffmpeg"):
        AudioSegment.converter = "ffmpeg"
        logger.info("Using FFmpeg from system PATH")
        return True
    
    logger.warning("FFmpeg not found! Audio processing may not work.")
    return False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup FFmpeg
ffmpeg_available = setup_ffmpeg()

# Create directories if they don't exist
os.makedirs("static/generated_audio", exist_ok=True)
os.makedirs("assets", exist_ok=True)

app = FastAPI(
    title="RSS to Audio News Briefing API",
    description="Convert RSS feeds into professional audio news briefings using Murf AI",
    version="1.1.0" # Version updated
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Murf API configuration
MURF_API_KEY = os.getenv('MURF_API_KEY')
MURF_API_URL = "https://api.murf.ai/v1/speech/generate"

# Path to my background music file
BACKGROUND_MUSIC_PATH = "assets/corporate-technology-196202.mp3"

# Request/Response Models
class GenerateBriefingRequest(BaseModel):
    feeds: List[str] = Field(..., description="List of RSS feed URLs", example=[
        "https://feeds.reuters.com/reuters/topNews",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"
    ])
    voice_id: Optional[str] = Field("en-US-natalie", description="Murf voice ID to use")
    audio_format: Optional[str] = Field("MP3", description="Audio format (MP3, WAV, FLAC)")
    # Added max_articles_per_feed parameter
    max_articles_per_feed: Optional[int] = Field(3, description="Max articles per feed", ge=1, le=10)


class BriefingResponse(BaseModel):
    success: bool
    audio_url: str
    briefing_text: str
    audio_length_seconds: float
    characters_used: int
    characters_remaining: int
    articles_count: int
    sources: List[str]

class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    details: Optional[str] = None

# Utility Functions
def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = ' '.join(text.split())
    text = text.replace('&amp;', 'and').replace('&lt;', '<').replace('&gt;', '>')
    return text

def get_source_name(feed_url: str) -> str:
    source_mapping = {
        "reuters": "Reuters", "nytimes": "New York Times", "techcrunch": "TechCrunch",
        "bbc": "BBC News", "cnn": "CNN", "wsj": "Wall Street Journal"
    }
    feed_lower = feed_url.lower()
    for key, name in source_mapping.items():
        if key in feed_lower:
            return name
    try:
        from urllib.parse import urlparse
        domain = urlparse(feed_url).netloc
        return domain.replace('www.', '').split('.')[0].title()
    except:
        return "News Source"

# Accepts max_per_feed to fetch a variable number of articles
def fetch_rss_articles(feed_urls: List[str], max_per_feed: int) -> tuple[List[dict], List[str]]:
    all_articles, sources_used = [], []
    for feed_url in feed_urls:
        try:
            feed = feedparser.parse(feed_url)
            if not feed.entries:
                logger.warning(f"No articles found in feed: {feed_url}")
                continue
            
            source_name = get_source_name(feed_url)
            if source_name not in sources_used:
                sources_used.append(source_name)

            for entry in feed.entries[:max_per_feed]: 
                title = clean_text(entry.get("title", ""))
                summary = clean_text(entry.get("summary", entry.get("description", "")))[:197] + "..."
                if title:
                    all_articles.append({'source': source_name, 'title': title, 'summary': summary})
        except Exception as e:
            logger.error(f"Error fetching feed {feed_url}: {e}")
            continue
    return all_articles, sources_used

def format_news_briefing(articles: List[dict]) -> str:
    if not articles:
        return "No news articles available at this time."
    current_date = datetime.now().strftime("%A, %B %d")
    briefing = f"Good morning from Durgapur. Here is your news briefing for {current_date}.\n\n"
    # Increased total article limit from 8 to 20
    for i, article in enumerate(articles[:20]):
        prefix = "From" if i == 0 else "Next, from"
        briefing += f"{prefix} {article['source']}... {article['title']}. {article['summary']}\n\n"
    briefing += "That concludes your news briefing. Have a great day!"
    return briefing

def mix_audio_with_music(speech_content: bytes) -> str:
    """Mixes speech with background music and returns the path to the final file."""
    try:
        logger.info("Starting audio mixing process...")
        if not ffmpeg_available:
            logger.warning("FFmpeg not available. Saving speech-only audio.")
            final_filename = f"briefing_{uuid.uuid4().hex}.mp3"
            final_filepath = f"static/generated_audio/{final_filename}"
            with open(final_filepath, 'wb') as f:
                f.write(speech_content)
            return f"/static/generated_audio/{final_filename}"
        
        speech_audio = AudioSegment.from_file(io.BytesIO(speech_content), format="mp3")
        
        if not os.path.exists(BACKGROUND_MUSIC_PATH):
            logger.warning(f"Background music file not found at {BACKGROUND_MUSIC_PATH}. Creating speech-only audio.")
            final_filename = f"briefing_{uuid.uuid4().hex}.mp3"
            final_filepath = f"static/generated_audio/{final_filename}"
            speech_audio.export(final_filepath, format="mp3")
            return f"/static/generated_audio/{final_filename}"

        logger.info(f"Loading background music from {BACKGROUND_MUSIC_PATH}")
        background_music = AudioSegment.from_file(BACKGROUND_MUSIC_PATH)
        speech_duration = len(speech_audio)
        
        if len(background_music) < speech_duration:
            loops_needed = (speech_duration // len(background_music)) + 1
            background_music = background_music * loops_needed
        
        background_music = background_music[:speech_duration]
        quiet_music = background_music - 15
        final_audio = quiet_music.overlay(speech_audio)

        final_filename = f"briefing_{uuid.uuid4().hex}.mp3"
        final_filepath = f"static/generated_audio/{final_filename}"
        
        logger.info(f"Exporting final audio to {final_filepath}")
        final_audio.export(final_filepath, format="mp3")
        logger.info(f"Successfully mixed audio and saved to {final_filepath}")

        return f"/static/generated_audio/{final_filename}"

    except Exception as e:
        logger.error(f"Error during audio mixing: {e}")
        try:
            logger.info("Attempting to save speech-only audio as fallback...")
            final_filename = f"briefing_{uuid.uuid4().hex}.mp3"
            final_filepath = f"static/generated_audio/{final_filename}"
            with open(final_filepath, 'wb') as f:
                f.write(speech_content)
            logger.info(f"Successfully saved speech-only audio to {final_filepath}")
            return f"/static/generated_audio/{final_filename}"
        except Exception as fallback_error:
            logger.error(f"Fallback audio save also failed: {fallback_error}")
            raise HTTPException(status_code=500, detail=f"Failed to process audio: {str(e)}")

def generate_audio_with_murf(text: str, voice_id: str, audio_format: str) -> dict:
    """Send text to Murf, get audio, mix it with music, and return local URL."""
    logger.info(f"Generating audio with Murf API - {len(text)} characters")
    # Switched to standard 'api-key' header, which is less prone to issues.
    headers = {"Content-Type": "application/json", "api-key": MURF_API_KEY}
    payload = {"text": text, "voiceId": voice_id, "format": audio_format}
    
    try:
        response = requests.post(MURF_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        
        response_data = response.json()
        murf_audio_url = response_data.get("audioFile")
        if not murf_audio_url:
            raise HTTPException(status_code=500, detail="No audio file URL in Murf response")

        logger.info("Downloading speech audio from Murf...")
        speech_response = requests.get(murf_audio_url)
        speech_response.raise_for_status()
        
        final_audio_path = mix_audio_with_music(speech_response.content)

        return {
            "audio_url": final_audio_path,
            "audio_length_seconds": response_data.get("audioLengthInSeconds", 0),
            "characters_used": response_data.get("consumedCharacterCount", 0),
            "characters_remaining": response_data.get("remainingCharacterCount", 0)
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Murf API request failed: {e.response.text if e.response else e}")
        error_details = e.response.json().get("errorMessage", str(e)) if e.response else str(e)
        raise HTTPException(status_code=500, detail=f"Murf API communication error: {error_details}")

# API Endpoints
@app.post("/generate-briefing", response_model=BriefingResponse, tags=["Audio Generation"])
def generate_briefing(request: GenerateBriefingRequest):
    if not request.feeds:
        raise HTTPException(status_code=400, detail="No RSS feed URLs provided")
    if not MURF_API_KEY or 'PASTE_YOUR_API_KEY_HERE' in MURF_API_KEY:
        raise HTTPException(status_code=500, detail="Murf API key is not configured on the server.")
    
    try:
        # Pass the new parameter to the fetch function
        articles, sources = fetch_rss_articles(request.feeds, request.max_articles_per_feed)
        if not articles:
            raise HTTPException(status_code=400, detail="Could not find any articles from the provided feeds.")
        
        briefing_text = format_news_briefing(articles)
        
        audio_data = generate_audio_with_murf(
            text=briefing_text,
            voice_id=request.voice_id,
            audio_format=request.audio_format
        )
        
        return BriefingResponse(
            success=True,
            articles_count=len(articles),
            sources=sources,
            briefing_text=briefing_text,
            **audio_data
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in generate_briefing: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

# Other endpoints
@app.get("/info", tags=["Info"])
def root():
    return {"service": "RSS to Audio News Briefing API", "version": "1.1.0"}

@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy", 
        "murf_api_configured": bool(MURF_API_KEY and 'PASTE_YOUR_API_KEY_HERE' not in MURF_API_KEY),
        "ffmpeg_available": ffmpeg_available,
        "background_music_exists": os.path.exists(BACKGROUND_MUSIC_PATH)
    }

@app.get("/", include_in_schema=False)
async def read_index():
    return FileResponse('static/index.html')

app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting RSS to Audio News Briefing API")
    print("📖 API Documentation: http://localhost:8000/docs")
    print(f"🎵 FFmpeg available: {ffmpeg_available}")
    print(f"🎵 Background music exists: {os.path.exists(BACKGROUND_MUSIC_PATH)}")
    uvicorn.run(app, host="0.0.0.0", port=8000)