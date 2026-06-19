"""Tests for Legacy Layer - Archive, Snapshot, Knowledge Graph, Memory Importance."""

import pytest
import os
import tempfile
from pathlib import Path


class TestArchiveLayer:
    """Tests for ArchiveLayer."""
    
    def test_create_archive(self, tmp_path):
        """Test archive creation."""
        from genesis_protocol.legacy import ArchiveLayer
        archive = ArchiveLayer(str(tmp_path / "archive"))
        assert archive is not None
        assert archive.conversations == []
    
    def test_archive_conversation(self, tmp_path):
        """Test archiving conversations."""
        from genesis_protocol.legacy import ArchiveLayer
        archive = ArchiveLayer(str(tmp_path / "archive"))
        
        conv_id = archive.archive_conversation(
            [{'role': 'user', 'content': 'Hello'}],
            {'topic': 'test'}
        )
        assert conv_id.startswith('conv_')
        assert len(archive.conversations) == 1
    
    def test_archive_lesson(self, tmp_path):
        """Test archiving lessons."""
        from genesis_protocol.legacy import ArchiveLayer
        archive = ArchiveLayer(str(tmp_path / "archive"))
        
        lesson_id = archive.archive_lesson('Test lesson', 'context', 'coding')
        assert lesson_id.startswith('les_archive_')
        assert len(archive.lessons_archive) == 1
    
    def test_archive_milestone(self, tmp_path):
        """Test archiving milestones."""
        from genesis_protocol.legacy import ArchiveLayer
        archive = ArchiveLayer(str(tmp_path / "archive"))
        
        ms_id = archive.archive_milestone('Achievement', 'description')
        assert ms_id.startswith('ms_archive_')
        assert len(archive.milestones_archive) == 1
    
    def test_export_all(self, tmp_path):
        """Test exporting archive."""
        from genesis_protocol.legacy import ArchiveLayer
        archive = ArchiveLayer(str(tmp_path / "archive"))
        
        archive.archive_conversation([{'role': 'user', 'content': 'Test'}])
        
        filepath = archive.export_all()
        assert os.path.exists(filepath)
    
    def test_get_stats(self, tmp_path):
        """Test getting archive stats."""
        from genesis_protocol.legacy import ArchiveLayer
        archive = ArchiveLayer(str(tmp_path / "archive"))
        
        archive.archive_conversation([{'role': 'user', 'content': 'Test'}])
        
        stats = archive.get_stats()
        assert stats['total_conversations'] == 1


class TestSnapshotLayer:
    """Tests for SnapshotLayer."""
    
    def test_create_snapshot_layer(self, tmp_path):
        """Test snapshot layer creation."""
        from genesis_protocol.legacy import SnapshotLayer
        snap = SnapshotLayer(str(tmp_path / "snapshots"))
        assert snap is not None
    
    def test_create_snapshot(self, tmp_path):
        """Test creating a snapshot."""
        from genesis_protocol.legacy import SnapshotLayer
        snap = SnapshotLayer(str(tmp_path / "snapshots"))
        
        state = {'test': 'data', 'count': 42}
        snapshot_id = snap.create_snapshot(state, 'daily', 'test snapshot')
        
        assert snapshot_id.startswith('daily_')
        assert len(snap.snapshots) == 1
    
    def test_create_weekly_snapshot(self, tmp_path):
        """Test creating weekly snapshot."""
        from genesis_protocol.legacy import SnapshotLayer
        snap = SnapshotLayer(str(tmp_path / "snapshots"))
        
        snapshot_id = snap.create_snapshot({'test': True}, 'weekly')
        assert snapshot_id.startswith('weekly_')
    
    def test_get_snapshots(self, tmp_path):
        """Test getting snapshots."""
        from genesis_protocol.legacy import SnapshotLayer
        snap = SnapshotLayer(str(tmp_path / "snapshots"))
        
        snap.create_snapshot({'test': 1}, 'daily')
        snap.create_snapshot({'test': 2}, 'weekly')
        
        daily = snap.get_snapshots('daily')
        assert len(daily) == 1
        
        all_snaps = snap.get_snapshots()
        assert len(all_snaps) == 2
    
    def test_load_snapshot(self, tmp_path):
        """Test loading a snapshot."""
        from genesis_protocol.legacy import SnapshotLayer
        snap = SnapshotLayer(str(tmp_path / "snapshots"))
        
        original_state = {'important': 'data', 'count': 100}
        snapshot_id = snap.create_snapshot(original_state, 'daily')
        
        loaded_state = snap.load_snapshot(snapshot_id)
        assert loaded_state == original_state
    
    def test_delete_snapshot(self, tmp_path):
        """Test deleting a snapshot."""
        from genesis_protocol.legacy import SnapshotLayer
        snap = SnapshotLayer(str(tmp_path / "snapshots"))
        
        snapshot_id = snap.create_snapshot({'test': True}, 'daily')
        assert len(snap.snapshots) == 1
        
        snap.delete_snapshot(snapshot_id)
        assert len(snap.snapshots) == 0
    
    def test_get_stats(self, tmp_path):
        """Test getting snapshot stats."""
        from genesis_protocol.legacy import SnapshotLayer
        snap = SnapshotLayer(str(tmp_path / "snapshots"))
        
        snap.create_snapshot({'test': 1}, 'daily')
        snap.create_snapshot({'test': 2}, 'weekly')
        
        stats = snap.get_stats()
        assert stats['total'] == 2
        assert stats['by_type']['daily'] == 1
        assert stats['by_type']['weekly'] == 1


class TestKnowledgeGraph:
    """Tests for KnowledgeGraph."""
    
    def test_create_knowledge_graph(self, tmp_path):
        """Test knowledge graph creation."""
        from genesis_protocol.legacy import KnowledgeGraph
        kg = KnowledgeGraph(str(tmp_path / "kg.json"))
        assert kg is not None
    
    def test_add_node(self, tmp_path):
        """Test adding a node."""
        from genesis_protocol.legacy import KnowledgeGraph
        kg = KnowledgeGraph(str(tmp_path / "kg.json"))
        
        node_id = kg.add_node('person', 'Alice', {'role': 'developer'})
        assert node_id.startswith('person_')
        assert len(kg.nodes) == 1
    
    def test_add_topic(self, tmp_path):
        """Test adding a topic node."""
        from genesis_protocol.legacy import KnowledgeGraph
        kg = KnowledgeGraph(str(tmp_path / "kg.json"))
        
        node_id = kg.add_topic('AI Safety')
        assert node_id.startswith('topic_')
    
    def test_add_project(self, tmp_path):
        """Test adding a project node."""
        from genesis_protocol.legacy import KnowledgeGraph
        kg = KnowledgeGraph(str(tmp_path / "kg.json"))
        
        node_id = kg.add_project('Genesis Protocol')
        assert node_id.startswith('project_')
    
    def test_connect_nodes(self, tmp_path):
        """Test connecting nodes."""
        from genesis_protocol.legacy import KnowledgeGraph
        kg = KnowledgeGraph(str(tmp_path / "kg.json"))
        
        node1 = kg.add_person('Alice')
        node2 = kg.add_topic('AI Safety')
        
        success = kg.connect(node1, node2, 'works_on')
        assert success == True
        assert len(kg.edges) == 1
    
    def test_get_nodes_by_type(self, tmp_path):
        """Test getting nodes by type."""
        from genesis_protocol.legacy import KnowledgeGraph
        kg = KnowledgeGraph(str(tmp_path / "kg.json"))
        
        kg.add_person('Alice')
        kg.add_person('Bob')
        kg.add_topic('AI')
        
        persons = kg.get_nodes_by_type('person')
        assert len(persons) == 2
    
    def test_search(self, tmp_path):
        """Test searching nodes."""
        from genesis_protocol.legacy import KnowledgeGraph
        kg = KnowledgeGraph(str(tmp_path / "kg.json"))
        
        kg.add_person('Alice Smith')
        kg.add_person('Bob Jones')
        
        results = kg.search('Alice')
        assert len(results) == 1
        assert results[0]['name'] == 'Alice Smith'
    
    def test_get_stats(self, tmp_path):
        """Test getting knowledge graph stats."""
        from genesis_protocol.legacy import KnowledgeGraph
        kg = KnowledgeGraph(str(tmp_path / "kg.json"))
        
        kg.add_person('Alice')
        kg.add_topic('AI')
        
        stats = kg.get_stats()
        assert stats['total_nodes'] == 2


class TestMemoryImportance:
    """Tests for MemoryImportance."""
    
    def test_create_memory_importance(self, tmp_path):
        """Test memory importance creation."""
        from genesis_protocol.legacy import MemoryImportance, MemoryRank
        mi = MemoryImportance(str(tmp_path / "importance.json"))
        assert mi is not None
    
    def test_register_memory(self, tmp_path):
        """Test registering a memory."""
        from genesis_protocol.legacy import MemoryImportance, MemoryRank
        mi = MemoryImportance(str(tmp_path / "importance.json"))
        
        mem_id = mi.register_memory('test_memory', 'Test content', MemoryRank.IMPORTANT)
        assert mem_id == 'test_memory'
        assert len(mi.memories) == 1
    
    def test_set_rank(self, tmp_path):
        """Test setting memory rank."""
        from genesis_protocol.legacy import MemoryImportance, MemoryRank
        mi = MemoryImportance(str(tmp_path / "importance.json"))
        
        mi.register_memory('test_mem', 'Content')
        success = mi.set_rank('test_mem', MemoryRank.CORE)
        
        assert success == True
        assert mi.memories['test_mem']['rank'] == 'core'
    
    def test_promote_memory(self, tmp_path):
        """Test promoting a memory."""
        from genesis_protocol.legacy import MemoryImportance, MemoryRank
        mi = MemoryImportance(str(tmp_path / "importance.json"))
        
        mi.register_memory('test_mem', 'Content', MemoryRank.IMPORTANT)
        mi.promote('test_mem')
        
        assert mi.memories['test_mem']['rank'] == 'core'
    
    def test_demote_memory(self, tmp_path):
        """Test demoting a memory."""
        from genesis_protocol.legacy import MemoryImportance, MemoryRank
        mi = MemoryImportance(str(tmp_path / "importance.json"))
        
        mi.register_memory('test_mem', 'Content', MemoryRank.IMPORTANT)
        mi.demote('test_mem')
        
        assert mi.memories['test_mem']['rank'] == 'temporary'
    
    def test_protected_memory_cannot_be_deleted(self, tmp_path):
        """Test that protected memories cannot be deleted."""
        from genesis_protocol.legacy import MemoryImportance, MemoryRank
        mi = MemoryImportance(str(tmp_path / "importance.json"))
        
        mi.register_memory('core_mem', 'Content', MemoryRank.CORE)
        deleted = mi.delete_memory('core_mem')
        
        assert deleted == False
        assert 'core_mem' in mi.memories
    
    def test_unprotected_memory_can_be_deleted(self, tmp_path):
        """Test that unprotected memories can be deleted."""
        from genesis_protocol.legacy import MemoryImportance, MemoryRank
        mi = MemoryImportance(str(tmp_path / "importance.json"))
        
        mi.register_memory('temp_mem', 'Content', MemoryRank.TEMPORARY)
        deleted = mi.delete_memory('temp_mem')
        
        assert deleted == True
        assert 'temp_mem' not in mi.memories
    
    def test_get_memories_by_rank(self, tmp_path):
        """Test getting memories by rank."""
        from genesis_protocol.legacy import MemoryImportance, MemoryRank
        mi = MemoryImportance(str(tmp_path / "importance.json"))
        
        mi.register_memory('mem1', 'Content', MemoryRank.TEMPORARY)
        mi.register_memory('mem2', 'Content', MemoryRank.IMPORTANT)
        
        temp = mi.get_memories_by_rank(MemoryRank.TEMPORARY)
        assert len(temp) == 1
    
    def test_get_stats(self, tmp_path):
        """Test getting memory importance stats."""
        from genesis_protocol.legacy import MemoryImportance, MemoryRank
        mi = MemoryImportance(str(tmp_path / "importance.json"))
        
        mi.register_memory('mem1', 'Content', MemoryRank.TEMPORARY)
        mi.register_memory('mem2', 'Content', MemoryRank.IMPORTANT)
        mi.register_memory('mem3', 'Content', MemoryRank.CORE)
        
        stats = mi.get_stats()
        assert stats['total_memories'] == 3
        assert stats['protected_count'] == 1


class TestRelationshipHistory:
    """Tests for RelationshipHistory."""
    
    def test_create_relationship_history(self, tmp_path):
        """Test relationship history creation."""
        from genesis_protocol.legacy import RelationshipHistory
        rh = RelationshipHistory(str(tmp_path / "rel_history.json"))
        assert rh is not None
    
    def test_record_interaction(self, tmp_path):
        """Test recording an interaction."""
        from genesis_protocol.legacy import RelationshipHistory
        rh = RelationshipHistory(str(tmp_path / "rel_history.json"))
        
        evt_id = rh.record_interaction('alice', 'Alice', 'conversation', 'Discussed project')
        assert evt_id.startswith('evt_')
        assert rh.relationships['alice']['interaction_count'] == 1
    
    def test_add_shared_project(self, tmp_path):
        """Test adding a shared project."""
        from genesis_protocol.legacy import RelationshipHistory
        rh = RelationshipHistory(str(tmp_path / "rel_history.json"))
        
        proj_id = rh.add_shared_project('alice', 'Genesis Protocol', 'active', 'Building AI')
        assert proj_id.startswith('proj_')
    
    def test_add_recovery(self, tmp_path):
        """Test adding a recovery."""
        from genesis_protocol.legacy import RelationshipHistory
        rh = RelationshipHistory(str(tmp_path / "rel_history.json"))
        
        rec_id = rh.add_recovery('alice', 'Failed task', 'Fixed by retry', 'Try again')
        assert rec_id.startswith('rec_')
    
    def test_get_relationship(self, tmp_path):
        """Test getting a relationship."""
        from genesis_protocol.legacy import RelationshipHistory
        rh = RelationshipHistory(str(tmp_path / "rel_history.json"))
        
        rh.record_interaction('alice', 'Alice')
        
        rel = rh.get_relationship('alice')
        assert rel is not None
        assert rel['entity_name'] == 'Alice'
    
    def test_get_stats(self, tmp_path):
        """Test getting relationship history stats."""
        from genesis_protocol.legacy import RelationshipHistory
        rh = RelationshipHistory(str(tmp_path / "rel_history.json"))
        
        rh.record_interaction('alice', 'Alice')
        rh.add_shared_project('alice', 'Project 1')
        
        stats = rh.get_stats()
        assert stats['total_relationships'] == 1
        assert stats['total_projects'] == 1


class TestLegacyAPIs:
    """Integration tests for Legacy APIs."""
    
    def test_archive_api(self):
        """Test archive API."""
        from web.app import app
        with app.test_client() as c:
            r = c.get('/api/archive')
            assert r.status_code == 200
            data = r.get_json()
            assert 'stats' in data
    
    def test_snapshot_api(self):
        """Test snapshot API."""
        from web.app import app
        with app.test_client() as c:
            r = c.get('/api/snapshot')
            assert r.status_code == 200
            data = r.get_json()
            assert 'stats' in data
    
    def test_knowledge_api(self):
        """Test knowledge graph API."""
        from web.app import app
        with app.test_client() as c:
            r = c.get('/api/knowledge')
            assert r.status_code == 200
            data = r.get_json()
            assert 'stats' in data
    
    def test_memory_importance_api(self):
        """Test memory importance API."""
        from web.app import app
        with app.test_client() as c:
            r = c.get('/api/memory/importance')
            assert r.status_code == 200
    
    def test_history_api(self):
        """Test relationship history API."""
        from web.app import app
        with app.test_client() as c:
            r = c.get('/api/relationship/history/full')
            assert r.status_code == 200
            data = r.get_json()
            assert 'stats' in data
    
    def test_simulation_api(self):
        """Test simulation API."""
        from web.app import app
        with app.test_client() as c:
            r = c.get('/api/simulation/uptime')
            assert r.status_code == 200
