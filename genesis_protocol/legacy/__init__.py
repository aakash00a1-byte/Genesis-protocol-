"""GLUTTONY Legacy Module - Ω+2

Preserves identity and continuity across years, devices and failures."""

from .archive import ArchiveLayer, get_archive_layer
from .snapshot import SnapshotLayer, get_snapshot_layer
from .knowledge_graph import KnowledgeGraph, get_knowledge_graph
from .memory_importance import MemoryImportance, MemoryRank, get_memory_importance
from .relationship_history import RelationshipHistory, get_relationship_history
from .cross_device import CrossDeviceContinuity, get_cross_device_continuity
from .legacy_books import LegacyBooks, get_legacy_books

__all__ = [
    'ArchiveLayer', 'get_archive_layer',
    'SnapshotLayer', 'get_snapshot_layer',
    'KnowledgeGraph', 'get_knowledge_graph',
    'MemoryImportance', 'MemoryRank', 'get_memory_importance',
    'RelationshipHistory', 'get_relationship_history',
    'CrossDeviceContinuity', 'get_cross_device_continuity',
    'LegacyBooks', 'get_legacy_books'
]
