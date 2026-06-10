"""Genesis Protocol - Memory Configuration"""

from dataclasses import dataclass

from genesis_protocol.config import VectorDBType


@dataclass
class MemoryConfig:
    """Memory system configuration."""
    
    # Vector database
    vector_db_type: VectorDBType = VectorDBType.CHROMA
    chroma_db_path: str = "./data/chroma_db"
    vector_dimensions: int = 1536
    vector_similarity_threshold: float = 0.75
    
    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_session_ttl: int = 86400  # 24 hours
    
    # Conversation
    max_conversation_history: int = 100
    max_messages_per_conversation: int = 1000
    
    # Vector store
    enable_vector_search: bool = True
    vector_search_limit: int = 5
    
    # Caching
    enable_caching: bool = True
    cache_ttl_seconds: int = 3600  # 1 hour
    
    @classmethod
    def from_env(cls) -> "MemoryConfig":
        """Create from environment variables."""
        import os
        return cls(
            vector_db_type=VectorDBType(os.getenv("VECTOR_DB_TYPE", "chroma")),
            chroma_db_path=os.getenv("CHROMA_DB_PATH", "./data/chroma_db"),
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_password=os.getenv("REDIS_PASSWORD", ""),
            max_conversation_history=int(os.getenv("MAX_CONVERSATION_HISTORY", "100")),
        )