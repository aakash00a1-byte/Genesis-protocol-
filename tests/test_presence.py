"""Tests for Presence Layer - Timeline, Relationship, Wisdom, Dream, Continuity."""

import pytest
import os
import tempfile
import time
from pathlib import Path


class TestTimelineMemory:
    """Tests for TimelineMemory."""
    
    def test_create_timeline(self, tmp_path):
        """Test timeline creation."""
        from genesis_protocol.gluttony_os import TimelineMemory
        storage = str(tmp_path / "timeline.json")
        tm = TimelineMemory(storage)
        assert tm is not None
        assert tm.events == []
    
    def test_add_event(self, tmp_path):
        """Test adding events."""
        from genesis_protocol.gluttony_os import TimelineMemory
        storage = str(tmp_path / "timeline.json")
        tm = TimelineMemory(storage)
        
        event_id = tm.add_event('test', 'Test Event', 'Description', {'key': 'value'})
        assert event_id.startswith('evt_')
        assert len(tm.events) == 1
        assert tm.events[0]['title'] == 'Test Event'
    
    def test_add_milestone(self, tmp_path):
        """Test adding milestones."""
        from genesis_protocol.gluttony_os import TimelineMemory
        storage = str(tmp_path / "timeline.json")
        tm = TimelineMemory(storage)
        
        ms_id = tm.add_milestone('Achievement', 'Achieved goal', 'success')
        assert ms_id.startswith('ms_')
        assert len(tm.milestones) == 1
    
    def test_add_recovery(self, tmp_path):
        """Test adding recoveries."""
        from genesis_protocol.gluttony_os import TimelineMemory
        storage = str(tmp_path / "timeline.json")
        tm = TimelineMemory(storage)
        
        rec_id = tm.add_recovery('Failed task', 'Fixed by retry', 'Try again')
        assert rec_id.startswith('rec_')
        assert len(tm.recoveries) == 1
    
    def test_add_lesson(self, tmp_path):
        """Test adding lessons."""
        from genesis_protocol.gluttony_os import TimelineMemory
        storage = str(tmp_path / "timeline.json")
        tm = TimelineMemory(storage)
        
        lesson_id = tm.add_lesson('coding', 'Test before deploy', 'production bug')
        assert lesson_id.startswith('les_')
        assert len(tm.lessons) == 1
    
    def test_get_timeline(self, tmp_path):
        """Test getting timeline."""
        from genesis_protocol.gluttony_os import TimelineMemory
        storage = str(tmp_path / "timeline.json")
        tm = TimelineMemory(storage)
        
        tm.add_event('test', 'Event 1', 'Desc 1')
        tm.add_event('test', 'Event 2', 'Desc 2')
        
        timeline = tm.get_timeline(10)
        assert len(timeline) >= 2
    
    def test_get_stats(self, tmp_path):
        """Test getting stats."""
        from genesis_protocol.gluttony_os import TimelineMemory
        storage = str(tmp_path / "timeline.json")
        tm = TimelineMemory(storage)
        
        # Clear any existing data
        tm._init_empty()
        tm._save()
        
        tm.add_event('test', 'Test', 'Test')
        tm.add_milestone('Test', 'Test', 'test')
        
        stats = tm.get_stats()
        # Note: add_milestone also adds an event internally
        assert stats['total_events'] == 2
        assert stats['total_milestones'] == 1


class TestRelationshipMemory:
    """Tests for RelationshipMemory."""
    
    def test_create_relationship(self, tmp_path):
        """Test relationship creation."""
        from genesis_protocol.gluttony_os import RelationshipMemory
        storage = str(tmp_path / "relationship.json")
        rm = RelationshipMemory(storage)
        assert rm is not None
        assert rm.creator_name == "Creator"
    
    def test_set_creator_name(self, tmp_path):
        """Test setting creator name."""
        from genesis_protocol.gluttony_os import RelationshipMemory
        storage = str(tmp_path / "relationship.json")
        rm = RelationshipMemory(storage)
        
        rm.set_creator_name("Alice")
        assert rm.creator_name == "Alice"
    
    def test_record_preference(self, tmp_path):
        """Test recording preferences."""
        from genesis_protocol.gluttony_os import RelationshipMemory
        storage = str(tmp_path / "relationship.json")
        rm = RelationshipMemory(storage)
        
        rm.record_preference('dark_mode', True)
        assert rm.preferences['dark_mode'] == True
    
    def test_add_topic(self, tmp_path):
        """Test adding topics."""
        from genesis_protocol.gluttony_os import RelationshipMemory
        storage = str(tmp_path / "relationship.json")
        rm = RelationshipMemory(storage)
        
        rm.add_topic('AI Safety', 'discussion about safety')
        assert len(rm.long_term_topics) == 1
        assert rm.long_term_topics[0]['topic'] == 'AI Safety'
    
    def test_add_pattern(self, tmp_path):
        """Test adding patterns."""
        from genesis_protocol.gluttony_os import RelationshipMemory
        storage = str(tmp_path / "relationship.json")
        rm = RelationshipMemory(storage)
        
        pattern_id = rm.add_pattern('coding', 'writes tests first')
        assert pattern_id.startswith('pat_')
        assert len(rm.recurring_patterns) == 1
    
    def test_record_interaction(self, tmp_path):
        """Test recording interactions."""
        from genesis_protocol.gluttony_os import RelationshipMemory
        storage = str(tmp_path / "relationship.json")
        rm = RelationshipMemory(storage)
        
        rm.record_interaction()
        rm.record_interaction()
        assert rm.interaction_count == 2
    
    def test_get_summary(self, tmp_path):
        """Test getting relationship summary."""
        from genesis_protocol.gluttony_os import RelationshipMemory
        storage = str(tmp_path / "relationship.json")
        rm = RelationshipMemory(storage)
        
        rm.set_creator_name("Bob")
        rm.record_interaction()
        
        summary = rm.get_relationship_summary()
        assert summary['creator_name'] == "Bob"
        assert summary['interaction_count'] == 1


class TestWisdomLayer:
    """Tests for WisdomLayer."""
    
    def test_create_wisdom(self, tmp_path):
        """Test wisdom layer creation."""
        from genesis_protocol.gluttony_os import WisdomLayer
        storage = str(tmp_path / "wisdom.json")
        w = WisdomLayer(storage)
        assert w is not None
        assert w.facts == []
    
    def test_add_fact(self, tmp_path):
        """Test adding facts."""
        from genesis_protocol.gluttony_os import WisdomLayer
        storage = str(tmp_path / "wisdom.json")
        w = WisdomLayer(storage)
        
        fact_id = w.add_fact('2+2=4', 'math', 1.0)
        assert fact_id.startswith('fact_')
        assert len(w.facts) == 1
        assert w.facts[0]['statement'] == '2+2=4'
    
    def test_add_assumption(self, tmp_path):
        """Test adding assumptions."""
        from genesis_protocol.gluttony_os import WisdomLayer
        storage = str(tmp_path / "wisdom.json")
        w = WisdomLayer(storage)
        
        assm_id = w.add_assumption('Probably sunny tomorrow', 'season', 0.6)
        assert assm_id.startswith('assm_')
        assert len(w.assumptions) == 1
    
    def test_add_belief(self, tmp_path):
        """Test adding beliefs."""
        from genesis_protocol.gluttony_os import WisdomLayer
        storage = str(tmp_path / "wisdom.json")
        w = WisdomLayer(storage)
        
        belief_id = w.add_belief('AI will help humanity', 'positive trends', 0.8)
        assert belief_id.startswith('bel_')
        assert len(w.beliefs) == 1
    
    def test_add_unknown(self, tmp_path):
        """Test adding unknowns."""
        from genesis_protocol.gluttony_os import WisdomLayer
        storage = str(tmp_path / "wisdom.json")
        w = WisdomLayer(storage)
        
        unk_id = w.add_unknown('What is consciousness?', 'philosophy')
        assert unk_id.startswith('unk_')
        assert len(w.unknowns) == 1
    
    def test_get_wisdom_summary(self, tmp_path):
        """Test getting wisdom summary."""
        from genesis_protocol.gluttony_os import WisdomLayer
        storage = str(tmp_path / "wisdom.json")
        w = WisdomLayer(storage)
        
        w.add_fact('Test', 'test')
        w.add_belief('Test belief', 'test')
        
        summary = w.get_wisdom_summary()
        assert summary['facts_count'] == 1
        assert summary['beliefs_count'] == 1


class TestDreamMode:
    """Tests for DreamMode."""
    
    def test_create_dream_mode(self):
        """Test dream mode creation."""
        from genesis_protocol.gluttony_os import DreamMode
        dm = DreamMode(idle_threshold_seconds=5)
        assert dm is not None
        assert dm.idle_threshold == 5
    
    def test_is_idle(self):
        """Test idle detection."""
        from genesis_protocol.gluttony_os import DreamMode
        dm = DreamMode(idle_threshold_seconds=1)
        
        # Should not be idle immediately
        assert not dm.is_idle()
        
        # Wait for threshold
        time.sleep(1.1)
        assert dm.is_idle()
    
    def test_record_activity(self):
        """Test recording activity."""
        from genesis_protocol.gluttony_os import DreamMode
        dm = DreamMode(idle_threshold_seconds=10)
        
        dm.record_activity()
        assert not dm.is_idle()
    
    def test_get_status(self):
        """Test getting status."""
        from genesis_protocol.gluttony_os import DreamMode
        dm = DreamMode()
        
        status = dm.get_status()
        assert 'is_active' in status
        assert 'is_idle' in status
        assert 'insights_generated' in status


class TestContinuityLayer:
    """Tests for ContinuityLayer."""
    
    def test_create_continuity(self, tmp_path):
        """Test continuity layer creation."""
        from genesis_protocol.gluttony_os import ContinuityLayer
        storage = str(tmp_path / "continuity.json")
        cl = ContinuityLayer(storage)
        assert cl is not None
    
    def test_save_and_restore_identity(self, tmp_path):
        """Test saving and restoring identity."""
        from genesis_protocol.gluttony_os import ContinuityLayer
        storage = str(tmp_path / "continuity.json")
        cl = ContinuityLayer(storage)
        
        identity_data = {'name': 'GLUTTONY', 'version': 'OS'}
        cl.save_identity(identity_data)
        
        restored = cl.restore_identity()
        assert restored == identity_data
    
    def test_save_and_restore_timeline(self, tmp_path):
        """Test saving and restoring timeline."""
        from genesis_protocol.gluttony_os import ContinuityLayer
        storage = str(tmp_path / "continuity.json")
        cl = ContinuityLayer(storage)
        
        timeline_state = {'events': [{'id': '1', 'title': 'Test'}], 'milestones': []}
        cl.save_timeline(timeline_state)
        
        restored = cl.restore_timeline()
        assert restored == timeline_state
    
    def test_get_continuity_status(self, tmp_path):
        """Test getting continuity status."""
        from genesis_protocol.gluttony_os import ContinuityLayer
        storage = str(tmp_path / "continuity.json")
        cl = ContinuityLayer(storage)
        
        cl.save_identity({'name': 'Test'})
        
        status = cl.get_continuity_status()
        assert status['has_identity'] == True
        assert status['has_timeline'] == False
    
    def test_simulate_uptime(self, tmp_path):
        """Test uptime simulation."""
        from genesis_protocol.gluttony_os import ContinuityLayer
        storage = str(tmp_path / "continuity.json")
        cl = ContinuityLayer(storage)
        
        result = cl.simulate_uptime(7)
        assert result['simulated_days'] == 7
    
    def test_record_restart(self, tmp_path):
        """Test recording restart."""
        from genesis_protocol.gluttony_os import ContinuityLayer
        storage = str(tmp_path / "continuity.json")
        cl = ContinuityLayer(storage)
        
        cl.record_restart()
        status = cl.get_continuity_status()
        assert status['uptime_simulation']['restarts'] == 1


class TestPresenceAPIs:
    """Integration tests for Presence Layer APIs."""
    
    def test_timeline_api(self):
        """Test timeline API integration."""
        from web.app import app
        with app.test_client() as c:
            # GET
            r = c.get('/api/timeline')
            assert r.status_code == 200
            data = r.get_json()
            assert 'timeline' in data
            assert 'stats' in data
    
    def test_journal_api(self):
        """Test journal API integration."""
        from web.app import app
        with app.test_client() as c:
            r = c.get('/api/journal')
            assert r.status_code == 200
            data = r.get_json()
            assert 'entries' in data
    
    def test_trust_api(self):
        """Test trust API integration."""
        from web.app import app
        with app.test_client() as c:
            r = c.get('/api/trust')
            assert r.status_code == 200
    
    def test_wisdom_api(self):
        """Test wisdom API integration."""
        from web.app import app
        with app.test_client() as c:
            r = c.get('/api/wisdom')
            assert r.status_code == 200
            data = r.get_json()
            assert 'facts' in data
            assert 'assumptions' in data
    
    def test_relationship_api(self):
        """Test relationship API integration."""
        from web.app import app
        with app.test_client() as c:
            r = c.get('/api/relationship')
            assert r.status_code == 200
            data = r.get_json()
            assert 'creator_name' in data
    
    def test_dream_api(self):
        """Test dream mode API integration."""
        from web.app import app
        with app.test_client() as c:
            r = c.get('/api/dream')
            assert r.status_code == 200
            data = r.get_json()
            assert 'is_idle' in data
    
    def test_continuity_api(self):
        """Test continuity API integration."""
        from web.app import app
        with app.test_client() as c:
            r = c.get('/api/continuity')
            assert r.status_code == 200
            data = r.get_json()
            assert 'has_identity' in data
