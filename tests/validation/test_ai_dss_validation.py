"""
Phase 3: AI & DSS Validation.
Tests Groq AI prompt engineering, JSON structure, confidence consistency, and multi-tier recommendations.
"""
import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.conf import settings
import json

from core.views import _filter_ai_analysis, _ai_analysis_fields
from core.models import AlertZone, UserProfile
from tests.factories import (
    SuperAdminUserFactory,
    EmergencyResponderFactory,
    UserFactory,
    AlertZoneFactory,
)

pytestmark = pytest.mark.django_db


class TestAIPromptEngineering:
    @pytest.mark.django_db
    def test_ai_analysis_returns_json_for_super_admin(self, api_client, super_admin, zone):
        api_client.force_authenticate(user=super_admin)
        with patch('core.views.Groq') as MockGroq:
            mock_client = MagicMock()
            MockGroq.return_value = mock_client
            mock_response = MagicMock()
            mock_response.choices[0].message.content.strip.return_value = json.dumps({
                'overall_risk': 'HIGH',
                'summary': 'Nairobi CBD experiencing moderate flooding.',
                'highest_risk_zone': 'Nairobi-CBD-001',
                'immediate_actions': ['Evacuate low-lying areas', 'Deploy emergency services', 'Monitor river levels'],
                '24h_outlook': 'Risk expected to increase with continued rainfall.',
                'safe_zones': ['Nairobi-Westlands-001', 'Nairobi-Upper-Hill-001'],
            })
            mock_client.chat.completions.create.return_value = mock_response
            response = api_client.post('/api/v1/ai-analysis/')
            assert response.status_code == 200
            data = response.json()
            assert data['source'] == 'groq'
            analysis = data['analysis']
            assert 'overall_risk' in analysis
            assert 'summary' in analysis
            assert 'highest_risk_zone' in analysis
            assert 'immediate_actions' in analysis
            assert '24h_outlook' in analysis
            assert 'safe_zones' in analysis

    @pytest.mark.django_db
    def test_ai_analysis_fallback_when_groq_unavailable(self, api_client, super_admin, zone):
        api_client.force_authenticate(user=super_admin)
        with patch('core.views.Groq', None):
            response = api_client.post('/api/v1/ai-analysis/')
            assert response.status_code == 200
            data = response.json()
            assert data['source'] == 'fallback'
            analysis = data['analysis']
            assert 'overall_risk' in analysis
            assert 'summary' in analysis

    @pytest.mark.django_db
    def test_ai_analysis_filtered_for_citizen(self, api_client, citizen, zone):
        api_client.force_authenticate(user=citizen)
        with patch('core.views.Groq') as MockGroq:
            mock_client = MagicMock()
            MockGroq.return_value = mock_client
            mock_response = MagicMock()
            mock_response.choices[0].message.content.strip.return_value = json.dumps({
                'overall_risk': 'MODERATE',
                'summary': 'Test summary',
                'highest_risk_zone': 'Test Zone',
                'immediate_actions': ['Action 1'],
                '24h_outlook': 'Test outlook',
                'safe_zones': ['Zone 1'],
            })
            mock_client.chat.completions.create.return_value = mock_response
            response = api_client.post('/api/v1/ai-analysis/')
            assert response.status_code == 200
            analysis = response.json()['analysis']
            assert 'overall_risk' in analysis
            assert 'summary' in analysis
            assert 'safe_zones' in analysis
            assert '24h_outlook' in analysis
            assert 'immediate_actions' not in analysis
            assert 'highest_risk_zone' not in analysis

    @pytest.mark.django_db
    def test_ai_analysis_full_for_emergency_responder(self, api_client, emergency_responder, zone):
        api_client.force_authenticate(user=emergency_responder)
        with patch('core.views.Groq') as MockGroq:
            mock_client = MagicMock()
            MockGroq.return_value = mock_client
            mock_response = MagicMock()
            mock_response.choices[0].message.content.strip.return_value = json.dumps({
                'overall_risk': 'HIGH',
                'summary': 'Test summary',
                'highest_risk_zone': 'Test Zone',
                'immediate_actions': ['Action 1'],
                '24h_outlook': 'Test outlook',
                'safe_zones': ['Zone 1'],
            })
            mock_client.chat.completions.create.return_value = mock_response
            response = api_client.post('/api/v1/ai-analysis/')
            assert response.status_code == 200
            analysis = response.json()['analysis']
            assert 'overall_risk' in analysis
            assert 'summary' in analysis
            assert 'safe_zones' in analysis
            assert '24h_outlook' in analysis
            assert 'immediate_actions' in analysis
            assert 'highest_risk_zone' in analysis

    @pytest.mark.django_db
    def test_ai_analysis_super_admin_gets_metadata(self, api_client, super_admin, zone):
        api_client.force_authenticate(user=super_admin)
        with patch('core.views.Groq') as MockGroq:
            mock_client = MagicMock()
            MockGroq.return_value = mock_client
            mock_response = MagicMock()
            mock_response.choices[0].message.content.strip.return_value = json.dumps({
                'overall_risk': 'HIGH',
                'summary': 'Test summary',
                'highest_risk_zone': 'Test Zone',
                'immediate_actions': ['Action 1'],
                '24h_outlook': 'Test outlook',
                'safe_zones': ['Zone 1'],
            })
            mock_client.chat.completions.create.return_value = mock_response
            response = api_client.post('/api/v1/ai-analysis/')
            assert response.status_code == 200
            data = response.json()
            assert 'data_confidence' in data
            assert 'source_metadata' in data


class TestAIDSSOutputStructure:
    @pytest.mark.django_db
    def test_dss_output_has_risk_classification(self, api_client, super_admin, zone):
        api_client.force_authenticate(user=super_admin)
        with patch('core.views.Groq') as MockGroq:
            mock_client = MagicMock()
            MockGroq.return_value = mock_client
            mock_response = MagicMock()
            mock_response.choices[0].message.content.strip.return_value = json.dumps({
                'overall_risk': 'CRITICAL',
                'summary': 'Severe flooding reported.',
                'highest_risk_zone': 'Zone A',
                'immediate_actions': ['Evacuate now'],
                '24h_outlook': 'Worsening conditions expected.',
                'safe_zones': ['Zone B'],
            })
            mock_client.chat.completions.create.return_value = mock_response
            response = api_client.post('/api/v1/ai-analysis/')
            data = response.json()
            assert data['analysis']['overall_risk'] in ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']

    @pytest.mark.django_db
    def test_dss_output_has_confidence_score(self, api_client, super_admin, zone):
        api_client.force_authenticate(user=super_admin)
        with patch('core.views.Groq') as MockGroq:
            mock_client = MagicMock()
            MockGroq.return_value = mock_client
            mock_response = MagicMock()
            mock_response.choices[0].message.content.strip.return_value = json.dumps({
                'overall_risk': 'HIGH',
                'summary': 'Test summary',
                'highest_risk_zone': 'Test Zone',
                'immediate_actions': ['Action 1'],
                '24h_outlook': 'Test outlook',
                'safe_zones': ['Zone 1'],
            })
            mock_client.chat.completions.create.return_value = mock_response
            response = api_client.post('/api/v1/ai-analysis/')
            data = response.json()
            assert 'data_confidence' in data
            assert data['data_confidence'] in ['high', 'medium', 'low', 'unknown']

    @pytest.mark.django_db
    def test_dss_output_has_evidence_and_predictions(self, api_client, super_admin, zone):
        api_client.force_authenticate(user=super_admin)
        with patch('core.views.Groq') as MockGroq:
            mock_client = MagicMock()
            MockGroq.return_value = mock_client
            mock_response = MagicMock()
            mock_response.choices[0].message.content.strip.return_value = json.dumps({
                'overall_risk': 'HIGH',
                'summary': 'Based on multi-source data: rainfall 45mm, river discharge 25m3/s.',
                'highest_risk_zone': 'Nairobi-CBD-001',
                'immediate_actions': ['Deploy pumps', 'Alert residents'],
                '24h_outlook': 'Risk decreasing in 24h.',
                '48h_outlook': 'Risk low in 48h.',
                'safe_zones': ['Westlands', 'Karen'],
            })
            mock_client.chat.completions.create.return_value = mock_response
            response = api_client.post('/api/v1/ai-analysis/')
            data = response.json()
            analysis = data['analysis']
            assert 'summary' in analysis
            assert '24h_outlook' in analysis
