"""
Enhanced AI prompts for flood risk decision support.
Provides structured JSON responses for flood analysis.
"""

import json
from typing import Dict, Any


def build_flood_analysis_prompt(region_name: str, features: dict, source_lines: list, zones: list) -> str:
    """Build structured prompt for flood risk analysis."""
    return f"""You are FloodGuard AI, an expert flood risk analyst for {region_name}.

MULTI-SOURCE DATA INTELLIGENCE:
Source Data:
{chr(10).join(source_lines) if source_lines else 'No external data available - use fallback logic'}

TOP MONITORED ZONES:
{chr(10).join([f'- {z.name}: {round((z.risk_score or 0) * 100, 1)}%' for z in zones[:5]]) or '- No zones monitored'}

COORDINATES: {features.get('zone_name', region_name)}

ANALYSIS REQUIREMENTS:
Respond ONLY in valid JSON format with these exact fields:

{{
  "overall_risk": "LOW|MODERATE|HIGH|CRITICAL",
  "summary": "2-3 sentences describing current flood conditions based on available data",
  "risk_explanation": "Why this risk level was determined - reference specific data sources",
  "confidence": "high|medium|low - based on number of working data sources",
  "highest_risk_zone": "zone name or nearest river/area",
  "immediate_actions": ["action1", "action2", "action3"],
  "authority_recommendations": ["action1", "action2"],
  "citizen_advice": ["action1", "action2"],
  "24h_outlook": "One sentence forecast for next 24 hours",
  "safe_zones": ["zone1", "zone2"],
  "infrastructure_risks": ["road", "bridge", "drainage"],
  "evacuation_needed": true|false
}}

IMPORTANT RULES:
- Never invent risk - base on actual data sources provided
- If data sources show low risk, respond with LOW
- Reference specific weather data (rainfall, discharge, humidity)
- Provide actionable recommendations for each audience
- Keep summary factual and concise
"""


def build_coordinate_analysis_prompt(lat: float, lon: float, data: dict) -> str:
    """Build prompt for coordinate-specific risk analysis."""
    weather = data.get('weather', {})
    zones = data.get('nearest_zones', [])
    h3 = data.get('h3_cell', {})
    
    return f"""You are FloodGuard AI analyzing flood risk at coordinates {lat}, {lon}.

DATA AVAILABLE:
- H3 Cell: {h3.get('h3_index', 'Unknown')}
- H3 Risk: {h3.get('risk_score', 0):.3f}
- Weather Sources: {weather.get('sources_available', 0)}
- River Discharge: {weather.get('river_discharge', 0):.2f} m³/s
- Recent Rainfall: {weather.get('rainfall_1h_mm', 0):.1f} mm/h

NEAREST ZONES:
{chr(10).join([f'- {z.get("name")}: {z.get("risk_score", 0):.1%}' for z in zones]) or '- No zones within 50km'}

Respond ONLY in valid JSON:
{{
  "overall_risk": "LOW|MODERATE|HIGH|CRITICAL",
  "summary": "Situation overview for this location",
  "risk_explanation": "Based on H3 cell and weather data",
  "confidence": "high|medium|low",
  "immediate_actions": ["Monitor conditions", "Avoid low areas"],
  "citizen_advice": ["Stay alert", "Report flooding"],
  "safe_routes": ["Use elevated roads"],
  "nearest_shelters": ["list zones under 0.4 risk"],
  "infrastructure_notes": ["Roads, bridges, drainage"]
}}
"""


def validate_ai_response(response: dict) -> dict:
    """Validate and normalize AI response to ensure all required fields."""
    required = [
        'overall_risk', 'summary', 'immediate_actions', '24h_outlook', 'safe_zones'
    ]
    
    defaults = {
        'risk_explanation': '',
        'confidence': 'medium',
        'authority_recommendations': [],
        'citizen_advice': [],
        'infrastructure_risks': [],
        'evacuation_needed': False,
    }
    
    for field in required:
        if field not in response:
            response[field] = 'Unknown' if field == 'overall_risk' else []
    
    for field, default in defaults.items():
        if field not in response:
            response[field] = default
    
    # Validate risk level
    if response.get('overall_risk') not in ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']:
        response['overall_risk'] = 'LOW'
    
    # Ensure lists
    for list_field in ['immediate_actions', 'safe_zones', 'authority_recommendations', 
                     'citizen_advice', 'infrastructure_risks']:
        if not isinstance(response.get(list_field), list):
            response[list_field] = []
    
    return response