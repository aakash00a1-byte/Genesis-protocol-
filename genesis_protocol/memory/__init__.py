"""Memory module for Genesis Protocol v1.1 - Enhanced with long-term memory"""

from .long_term_memory import (
    LongTermMemory,
    MemoryEntry,
    MemoryImportance,
    get_long_term_memory,
)
from .memory_summarizer import MemorySummarizer

__all__ = [
    'LongTermMemory',
    'MemoryEntry',
    'MemoryImportance',
    'MemorySummarizer',
    'get_long_term_memory',
]
