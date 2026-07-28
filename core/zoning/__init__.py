"""
FloodGuard Zoning Engine
Three-layer architecture:
- Layer 1: Administrative Boundaries
- Layer 2: H3 Spatial Grid Intelligence
- Layer 3: Dynamic Flood Zones with lifecycle management
"""

from .h3_intelligence import (
    get_or_create_h3_cell,
    get_h3_cells_for_bbox,
    get_neighboring_cells,
    build_h3_relationships,
    aggregate_to_resolution,
    get_cell_risk,
    update_cell_risk,
    get_h3_cell_stats,
    _get_h3_resolution,
)

from .dynamic_zoning import (
    generate_zone_from_weather,
    generate_zone_from_reports,
    generate_zone_from_discharge,
    generate_zone_from_rainfall,
    enhance_zone_with_satellite,
    create_authority_zone,
    merge_zones,
    split_zone,
    retire_expired_zones,
    archive_inactive_zones,
)

from .lifecycle import (
    transition_zone_state,
    evaluate_zone_transitions,
    process_lifecycle_for_all_zones,
    ZONE_STATES,
)

from .propagation import (
    propagate_flood,
    propagate_for_active_zones,
    get_propagation_for_zone,
)

from .location_engine import (
    process_user_location,
    batch_process_locations,
    get_user_location_history,
    check_geofence_entry,
    LocationEngine,
)

from .search_engine import (
    universal_search,
)

__all__ = [
    'get_or_create_h3_cell',
    'get_h3_cells_for_bbox',
    'get_neighboring_cells',
    'build_h3_relationships',
    'aggregate_to_resolution',
    'get_cell_risk',
    'update_cell_risk',
    'get_h3_cell_stats',
    '_get_h3_resolution',
    'generate_zone_from_weather',
    'generate_zone_from_reports',
    'generate_zone_from_discharge',
    'generate_zone_from_rainfall',
    'enhance_zone_with_satellite',
    'create_authority_zone',
    'merge_zones',
    'split_zone',
    'retire_expired_zones',
    'archive_inactive_zones',
    'transition_zone_state',
    'evaluate_zone_transitions',
    'process_lifecycle_for_all_zones',
    'ZONE_STATES',
    'propagate_flood',
    'propagate_for_active_zones',
    'get_propagation_for_zone',
    'process_user_location',
    'batch_process_locations',
    'get_user_location_history',
    'check_geofence_entry',
    'LocationEngine',
    'universal_search',
]
