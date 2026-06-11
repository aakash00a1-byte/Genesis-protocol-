"""
Genesis Protocol - Configuration Management

Centralized configuration system for all Genesis Protocol components.
Loads environment variables and provides type-safe access to configuration.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()


class AppEnvironment(Enum):
    """Application environment types."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class VectorDBType(Enum):
    """Supported vector database types."""
    CHROMA = "chroma"
    QDRANT = "qdrant"
    WEAVIATE = "weaviate"


@dataclass
class TelegramConfig:
    """Telegram bot configuration."""
    bot_token: str = ""
    bot_username: str = "Genesis_autonomousbot"
    api_id: Optional[str] = None
    api_hash: Optional[str] = None
    session_name: str = "genesis_session"
    
    def validate(self) -> bool:
        """Validate Telegram configuration."""
        return bool(self.bot_token)


@dataclass
class AIProviderConfig:
    """AI provider base configuration."""
    api_key: str = ""
    endpoint: Optional[str] = None
    timeout: int = 30
    max_retries: int = 3
    
    def is_configured(self) -> bool:
        """Check if provider is configured with API key."""
        return bool(self.api_key)


@dataclass
class GroqConfig(AIProviderConfig):
    """Groq AI provider configuration."""
    endpoint: str = "https://api.groq.com/openai/v1/chat/completions"
    default_model: str = "llama-3.3-70b-versatile"
    fast_model: str = "llama-3.3-70b-versatile"
    rate_limit_rpm: int = 30


@dataclass
class OpenAIConfig(AIProviderConfig):
    """OpenAI AI provider configuration."""
    endpoint: str = "https://api.openai.com/v1/chat/completions"
    default_model: str = "gpt-4o-mini"
    quality_model: str = "gpt-4o"
    rate_limit_rpm: int = 500


@dataclass
class GeminiConfig(AIProviderConfig):
    """Google Gemini AI provider configuration."""
    endpoint: str = "https://generativelanguage.googleapis.com/v1beta"
    default_model: str = "gemini-1.5-flash"
    quality_model: str = "gemini-1.5-pro"
    rate_limit_rpm: int = 60
    rate_limit_rpd: int = 1500


@dataclass
class HuggingFaceConfig(AIProviderConfig):
    """HuggingFace AI provider configuration."""
    endpoint: str = "https://api-inference.huggingface.co/models/"
    default_model: str = "meta-llama/Llama-3.1-70B-Instruct"
    timeout: int = 60


@dataclass
class ClaudeConfig(AIProviderConfig):
    """Anthropic Claude AI provider configuration."""
    endpoint: str = "https://api.anthropic.com/v1/messages"
    default_model: str = "claude-3-5-sonnet-20241022"
    quality_model: str = "claude-sonnet-4-20250514"
    fast_model: str = "claude-3-haiku-20240307"
    rate_limit_rpm: int = 50


@dataclass
class MemoryConfig:
    """Memory system configuration."""
    vector_db_type: VectorDBType = VectorDBType.CHROMA
    chroma_db_path: str = "./data/chroma_db"
    vector_dimensions: int = 1536
    vector_similarity_threshold: float = 0.75
    
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_session_ttl: int = 86400  # 24 hours
    
    max_conversation_history: int = 100


@dataclass
class TavilyConfig:
    """Tavily search API configuration."""
    api_key: str = ""
    endpoint: str = "https://api.tavily.com/search"
    search_depth: str = "basic"  # basic | advanced
    max_results: int = 10
    cache_ttl_hours: int = 24
    
    def is_configured(self) -> bool:
        """Check if Tavily is configured."""
        return bool(self.api_key)


@dataclass
class MakeComConfig:
    """Make.com webhook configuration."""
    webhook_url: str = ""
    api_key: str = ""
    
    def is_configured(self) -> bool:
        """Check if Make.com is configured."""
        return bool(self.webhook_url and self.api_key)


@dataclass
class VoiceConfig:
    """Voice processing configuration."""
    stt_provider: str = "whisper"  # whisper | deepgram | speechmatics
    stt_language: str = "auto"
    stt_model: str = "whisper-1"
    
    tts_provider: str = "elevenlabs"  # elevenlabs | gtts | azure
    tts_voice_id: str = "rachel"
    tts_speed: float = 0.95
    
    supported_formats: list = field(default_factory=lambda: ["ogg", "opus", "wav", "mp3", "m4a"])
    max_duration_seconds: int = 120
    max_file_size_mb: int = 10
    audio_sample_rate: int = 16000


@dataclass
class ImageConfig:
    """Image processing configuration."""
    vision_provider: str = "openai"  # openai | gemini | huggingface
    vision_model: str = "gpt-4o-mini"
    
    supported_formats: list = field(default_factory=lambda: ["jpg", "jpeg", "png", "gif", "webp", "bmp"])
    max_width: int = 4096
    max_height: int = 4096
    max_file_size_mb: int = 10
    
    ocr_enabled: bool = True
    ocr_language: str = "eng+spa+fra+deu"
    auto_enhance: bool = True
    remove_metadata: bool = True


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    max_messages_per_minute: int = 20
    max_messages_per_hour: int = 500
    max_image_size_mb: int = 10
    max_voice_duration_seconds: int = 120
    
    api_rate_limit: int = 100  # requests per minute


@dataclass
class SecurityConfig:
    """Security configuration."""
    allowed_origins: list = field(default_factory=lambda: ["http://localhost:8501", "http://localhost:3000"])
    app_secret_key: str = ""
    
    # Rate limiting
    enable_rate_limiting: bool = True
    enable_input_sanitization: bool = True
    
    # Encryption
    encrypt_at_rest: bool = True


@dataclass
class StreamlitConfig:
    """Streamlit dashboard configuration."""
    port: int = 8501
    secret_key: str = ""
    enabled: bool = True


@dataclass
class Config:
    """
    Main Genesis Protocol configuration class.
    
    Aggregates all sub-configuration classes and provides
    a single point of access for all configuration values.
    """
    # Environment
    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    app_debug: bool = True
    app_log_level: str = "INFO"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    
    # Sub-configurations
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    groq: GroqConfig = field(default_factory=GroqConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    huggingface: HuggingFaceConfig = field(default_factory=HuggingFaceConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    tavily: TavilyConfig = field(default_factory=TavilyConfig)
    make_com: MakeComConfig = field(default_factory=MakeComConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    image: ImageConfig = field(default_factory=ImageConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    streamlit: StreamlitConfig = field(default_factory=StreamlitConfig)
    
    # Channel Isolation Configuration
    telegram_enabled: bool = field(default_factory=lambda: os.getenv("TELEGRAM_ENABLED", "true").lower() == "true")
    telegram_admin_only: bool = field(default_factory=lambda: os.getenv("TELEGRAM_ADMIN_ONLY", "true").lower() == "true")
    telegram_admin_chat_id: Optional[int] = field(default_factory=lambda: int(os.getenv("TELEGRAM_ADMIN_CHAT_ID", "0")) or None)
    
    # Paths
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    data_dir: Path = field(default_factory=lambda: Path("./data"))
    
    @classmethod
    def from_env(cls) -> "Config":
        """
        Load configuration from environment variables.
        
        Returns:
            Config: Populated configuration instance
        """
        config = cls()
        
        # Environment
        config.app_env = AppEnvironment(os.getenv("APP_ENV", "development"))
        config.app_debug = os.getenv("APP_DEBUG", "true").lower() == "true"
        config.app_log_level = os.getenv("APP_LOG_LEVEL", "INFO")
        config.app_host = os.getenv("APP_HOST", "0.0.0.0")
        config.app_port = int(os.getenv("APP_PORT", "8000"))
        
        # Telegram
        config.telegram.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        config.telegram.bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "Genesis_autonomousbot")
        config.telegram.api_id = os.getenv("TELEGRAM_API_ID")
        config.telegram.api_hash = os.getenv("TELEGRAM_API_HASH")
        config.telegram.session_name = os.getenv("TELEGRAM_SESSION_NAME", "genesis_session")
        
        # Groq
        config.groq.api_key = os.getenv("GROQ_API_KEY", "")
        config.groq.default_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        
        # OpenAI
        config.openai.api_key = os.getenv("OPENAI_API_KEY", "")
        config.openai.default_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        
        # Gemini
        config.gemini.api_key = os.getenv("GEMINI_API_KEY", "")
        config.gemini.default_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        
        # HuggingFace
        config.huggingface.api_key = os.getenv("HUGGINGFACE_API_KEY", "")
        config.huggingface.default_model = os.getenv("HF_MODEL", "meta-llama/Llama-3.1-70B-Instruct")
        
        # Claude (Anthropic)
        config.claude.api_key = os.getenv("ANTHROPIC_API_KEY", "") or os.getenv("CLAUDE_API_KEY", "")
        config.claude.default_model = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
        
        # Memory
        config.memory.vector_db_type = VectorDBType(os.getenv("VECTOR_DB_TYPE", "chroma"))
        config.memory.chroma_db_path = os.getenv("CHROMA_DB_PATH", "./data/chroma_db")
        config.memory.vector_dimensions = int(os.getenv("VECTOR_DIMENSIONS", "1536"))
        config.memory.redis_host = os.getenv("REDIS_HOST", "localhost")
        config.memory.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        config.memory.redis_password = os.getenv("REDIS_PASSWORD", "")
        config.memory.max_conversation_history = int(os.getenv("MAX_CONVERSATION_HISTORY", "100"))
        
        # Tavily
        config.tavily.api_key = os.getenv("TAVILY_API_KEY", "")
        
        # Make.com
        config.make_com.webhook_url = os.getenv("MAKE_COM_WEBHOOK_URL", "")
        config.make_com.api_key = os.getenv("MAKE_COM_API_KEY", "")
        
        # Streamlit
        config.streamlit.port = int(os.getenv("STREAMLIT_PORT", "8501"))
        config.streamlit.secret_key = os.getenv("STREAMLIT_SECRET_KEY", "")
        config.streamlit.enabled = os.getenv("ENABLE_STREAMLIT", "true").lower() == "true"
        
        # Security
        config.security.app_secret_key = os.getenv("APP_SECRET_KEY", "")
        allowed = os.getenv("ALLOWED_ORIGINS", "http://localhost:8501,http://localhost:3000")
        config.security.allowed_origins = [s.strip() for s in allowed.split(",")]
        
        return config
    
    def validate(self) -> list[str]:
        """
        Validate configuration and return list of warnings.
        
        Returns:
            list[str]: List of validation warnings (empty if all OK)
        """
        warnings = []
        
        # Check critical providers
        if not self.groq.is_configured():
            warnings.append("Groq API key not configured - AI fallback chain will be affected")
        if not self.openai.is_configured():
            warnings.append("OpenAI API key not configured - AI fallback chain will be affected")
        if not self.gemini.is_configured():
            warnings.append("Gemini API key not configured - AI fallback chain will be affected")
        if not self.huggingface.is_configured():
            warnings.append("HuggingFace API key not configured - AI fallback chain will be affected")
        
        # Check Telegram
        if not self.telegram.validate():
            warnings.append("Telegram bot token not configured - bot will not function")
        
        # Check paths
        if not self.data_dir.exists():
            try:
                self.data_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                warnings.append(f"Cannot create data directory: {e}")
        
        return warnings
    
    def get_ai_provider_order(self) -> list[str]:
        """
        Get ordered list of AI providers to try.
        
        Returns:
            list[str]: Provider names in priority order
        """
        order = []
        if self.groq.is_configured():
            order.append("groq")
        if self.openai.is_configured():
            order.append("openai")
        if self.gemini.is_configured():
            order.append("gemini")
        if self.huggingface.is_configured():
            order.append("huggingface")
        return order


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get the global configuration instance.
    
    Returns:
        Config: Singleton configuration instance
    """
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reload_config() -> Config:
    """
    Reload configuration from environment.
    
    Returns:
        Config: New configuration instance
    """
    global _config
    _config = Config.from_env()
    return _config