"""Knowledge Graph - GLUTTONY Legacy

Connects people, topics, projects, memories, and lessons."""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Set, Any
from pathlib import Path


class KnowledgeGraph:
    """Graph-based knowledge storage connecting entities."""
    
    def __init__(self, storage_path: str = "data/legacy/knowledge_graph.json"):
        self.storage_path = storage_path
        self._ensure_storage()
        
        # Nodes: id -> {type, name, data, connections}
        self.nodes: Dict[str, Dict] = {}
        # Edges: (node1_id, node2_id) -> {type, weight, created_at}
        self.edges: Dict[tuple, Dict] = {}
        # Index by type
        self.type_index: Dict[str, Set[str]] = {
            'person': set(),
            'topic': set(),
            'project': set(),
            'memory': set(),
            'lesson': set(),
            'event': set()
        }
        
        self._load()
    
    def _ensure_storage(self):
        """Ensure storage directory exists."""
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        """Load knowledge graph from disk."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    self.nodes = data.get('nodes', {})
                    edges_raw = data.get('edges', {})
                    self.edges = {tuple(k.split('|')): v for k, v in edges_raw.items()}
                    self.type_index = data.get('type_index', self.type_index)
                    # Rebuild type_index from nodes
                    for node_id, node in self.nodes.items():
                        node_type = node.get('type')
                        if node_type and node_type in self.type_index:
                            self.type_index[node_type].add(node_id)
            except Exception:
                pass
    
    def _save(self):
        """Save knowledge graph to disk."""
        edges_raw = {f"{k[0]}|{k[1]}": v for k, v in self.edges.items()}
        data = {
            'nodes': self.nodes,
            'edges': edges_raw,
            'type_index': {k: list(v) for k, v in self.type_index.items()},
            'last_updated': datetime.now().isoformat()
        }
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_node(self, node_type: str, name: str, data: Dict = None) -> str:
        """Add a node to the knowledge graph."""
        node_id = f"{node_type}_{len(self.nodes)}_{int(datetime.now().timestamp())}"
        
        node = {
            'id': node_id,
            'type': node_type,
            'name': name,
            'data': data or {},
            'created_at': datetime.now().isoformat(),
            'connections': []
        }
        
        self.nodes[node_id] = node
        
        if node_type in self.type_index:
            self.type_index[node_type].add(node_id)
        
        self._save()
        return node_id
    
    def add_person(self, name: str, data: Dict = None) -> str:
        """Add a person node."""
        return self.add_node('person', name, data)
    
    def add_topic(self, name: str, data: Dict = None) -> str:
        """Add a topic node."""
        return self.add_node('topic', name, data)
    
    def add_project(self, name: str, data: Dict = None) -> str:
        """Add a project node."""
        return self.add_node('project', name, data)
    
    def add_memory(self, name: str, data: Dict = None) -> str:
        """Add a memory node."""
        return self.add_node('memory', name, data)
    
    def add_lesson(self, name: str, data: Dict = None) -> str:
        """Add a lesson node."""
        return self.add_node('lesson', name, data)
    
    def connect(self, node1_id: str, node2_id: str, 
                edge_type: str = 'related', weight: float = 1.0) -> bool:
        """Connect two nodes."""
        if node1_id not in self.nodes or node2_id not in self.nodes:
            return False
        
        edge_key = tuple(sorted([node1_id, node2_id]))
        
        self.edges[edge_key] = {
            'type': edge_type,
            'weight': weight,
            'created_at': datetime.now().isoformat()
        }
        
        # Update node connections
        if node1_id not in self.nodes[node2_id]['connections']:
            self.nodes[node2_id]['connections'].append(node1_id)
        if node2_id not in self.nodes[node1_id]['connections']:
            self.nodes[node1_id]['connections'].append(node2_id)
        
        self._save()
        return True
    
    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get a node by ID."""
        return self.nodes.get(node_id)
    
    def get_nodes_by_type(self, node_type: str) -> List[Dict]:
        """Get all nodes of a specific type."""
        node_ids = self.type_index.get(node_type, set())
        return [self.nodes[nid] for nid in node_ids if nid in self.nodes]
    
    def get_connections(self, node_id: str) -> List[Dict]:
        """Get all connections for a node."""
        if node_id not in self.nodes:
            return []
        
        connections = []
        for edge_key, edge_data in self.edges.items():
            if node_id in edge_key:
                other_id = edge_key[0] if edge_key[1] == node_id else edge_key[1]
                if other_id in self.nodes:
                    connections.append({
                        'node': self.nodes[other_id],
                        'edge': edge_data
                    })
        
        return connections
    
    def search(self, query: str, node_type: str = None) -> List[Dict]:
        """Search nodes by name."""
        results = []
        query_lower = query.lower()
        
        types_to_search = [node_type] if node_type else list(self.type_index.keys())
        
        for ntype in types_to_search:
            if ntype not in self.type_index:
                continue
            for node_id in self.type_index[ntype]:
                if node_id not in self.nodes:
                    continue
                node = self.nodes[node_id]
                if query_lower in node['name'].lower():
                    results.append(node)
        
        return results
    
    def get_graph(self) -> Dict:
        """Get the full knowledge graph."""
        return {
            'nodes': self.nodes,
            'edges': len(self.edges),
            'stats': self.get_stats()
        }
    
    def get_stats(self) -> Dict:
        """Get knowledge graph statistics."""
        stats = {
            'total_nodes': len(self.nodes),
            'total_edges': len(self.edges),
            'by_type': {}
        }
        
        for ntype, node_ids in self.type_index.items():
            count = sum(1 for nid in node_ids if nid in self.nodes)
            stats['by_type'][ntype] = count
        
        return stats


_knowledge_graph: Optional[KnowledgeGraph] = None


def get_knowledge_graph() -> KnowledgeGraph:
    """Get knowledge graph singleton."""
    global _knowledge_graph
    if _knowledge_graph is None:
        _knowledge_graph = KnowledgeGraph()
    return _knowledge_graph
