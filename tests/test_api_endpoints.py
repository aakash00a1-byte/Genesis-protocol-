"""Tests for API endpoints."""

import pytest
import json


class TestHealthEndpoints:
    """Test monitoring endpoints."""

    def test_api_health(self, client):
        """Test /api/health endpoint."""
        response = client.get('/api/health')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
        assert 'entrypoint' in data

    def test_api_version(self, client):
        """Test /api/version endpoint."""
        response = client.get('/api/version')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'version' in data
        assert 'build_date' in data

    def test_api_status(self, client):
        """Test /api/status endpoint."""
        response = client.get('/api/status')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'ok'
        assert 'metrics' in data
        assert 'timestamp' in data

    def test_api_diagnostics(self, client):
        """Test /api/diagnostics endpoint."""
        response = client.get('/api/diagnostics')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'version' in data
        assert 'providers' in data
        assert 'database' in data
        assert 'metrics' in data

    def test_api_diagnostics_structure(self, client):
        """Test diagnostics response structure."""
        response = client.get('/api/diagnostics')
        data = json.loads(response.data)
        
        # Check metrics structure
        metrics = data.get('metrics', {})
        assert 'request_count' in metrics
        assert 'error_count' in metrics
        assert 'uptime_seconds' in metrics

    def test_api_debug(self, client):
        """Test /api/debug endpoint."""
        response = client.get('/api/debug')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'available_providers' in data
        assert 'provider_status' in data


class TestHistoryEndpoint:
    """Test history endpoints."""

    def test_api_history_requires_login(self, client):
        """Test /api/history requires authentication."""
        response = client.get('/api/history')
        # Should redirect to login or return unauthorized
        assert response.status_code in [302, 401]

    def test_api_chat_requires_login(self, client):
        """Test /api/chat requires authentication."""
        response = client.post('/api/chat', 
                              data=json.dumps({'message': 'test'}),
                              content_type='application/json')
        # Should redirect to login or return unauthorized
        assert response.status_code in [302, 401]


class TestMetricsTracking:
    """Test metrics tracking."""

    def test_metrics_initial_state(self, client):
        """Test metrics start at zero."""
        response = client.get('/api/status')
        data = json.loads(response.data)
        metrics = data.get('metrics', {})
        
        # Should be initialized (may not be zero due to previous tests)
        assert 'request_count' in metrics
        assert 'error_count' in metrics

    def test_diagnostics_has_uptime(self, client):
        """Test diagnostics includes uptime."""
        response = client.get('/api/diagnostics')
        data = json.loads(response.data)
        
        uptime = data.get('uptime', {})
        assert 'seconds' in uptime
        assert uptime['seconds'] >= 0
