"""Configuration for agent models and constants."""
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

# Initialize Google GenAI client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Model configurations
LLM_MODEL = "gemini-3.1-pro-preview"  # Primary model
LLM_FALLBACK = "gemini-2.5-pro"  # Fallback model
IMAGE_MODEL = "gemini-3.1-flash-image-preview"  # Nano Banana 2

# QUIC/HTTP3 error patterns for graceful handling
QUIC_ERROR_PATTERNS = [
    'quic_protocol_error',
    'quic_network_idle_timeout',
    'quic_connection_refused',
    'h3 error',
    'http3',
    'protocol_error',
    'connection_closed',
    'stream_reset',
]

# Topic stopwords for relevance checking
TOPIC_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "in", "into", "is", "it", "its", "of", "on", "or", "our",
    "that", "the", "this", "to", "via", "we", "with",
}
