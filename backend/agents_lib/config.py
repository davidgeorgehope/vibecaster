"""Configuration for agent models and constants."""
# Models and the API client live in backend/xai_client.py.

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
