# FloodGuard Development TODO

## Current Task: Enhance Weather Widget with Live Satellite Data & Kenya Mapping

### High Priority

- [ ] Enhance weather_widget API endpoint to include satellite data integration
- [ ] Add real-time visual mapping capabilities for Kenya
- [ ] Integrate flood risk assessment based on satellite data
- [ ] Add GeoJSON data for Kenya-specific weather stations and flood zones
- [ ] Implement live data updates with satellite imagery

### Medium Priority

- [ ] Add weather prediction models using AI/ML
- [ ] Implement real-time weather alerts for Kenya regions
- [ ] Add historical weather data comparison
- [ ] Create interactive map with weather overlays

### Low Priority

- [ ] Add weather data export functionality
- [ ] Implement weather data caching for performance
- [ ] Add weather station health monitoring
- [ ] Create weather data visualization charts

## Completed Tasks

- [x] Endpoint audit completed (ENDPOINT_AUDIT_REPORT.md)
- [x] Django server running successfully
- [x] Basic weather widget API functional

## Notes

- Current weather widget returns basic weather data
- Satellite data model exists but not integrated with weather widget
- Kenya-specific mapping requires GeoJSON integration
- Real-time updates need WebSocket or polling implementation
