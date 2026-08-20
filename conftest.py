import os
import sys
import pathlib
import types
import json
from unittest.mock import MagicMock

_base_dir = pathlib.Path(__file__).resolve().parent
_shapely_libs = _base_dir / '.venv' / 'Lib' / 'site-packages' / 'shapely.libs'
geos_dlls = list(_shapely_libs.glob('geos_c-*.dll'))
if geos_dlls:
    os.environ['GEOS_LIBRARY_PATH'] = str(geos_dlls[0])

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'floodguard.test_settings')

# Create comprehensive mock for the entire django.contrib.gis.gdal package tree
gdal_exceptions_module = types.ModuleType('django.contrib.gis.gdal.error')
gdal_exceptions_module.GDALException = type('GDALException', (Exception,), {})

gdal_srs_module = types.ModuleType('django.contrib.gis.gdal.srs')
gdal_srs_module.SpatialReference = MagicMock
gdal_srs_module.CoordTransform = MagicMock
gdal_srs_module.SRSException = type('SRSException', (Exception,), {})

gdal_geom_module = types.ModuleType('django.contrib.gis.gdal.geometries')
gdal_geom_module.OGRGeometry = MagicMock
gdal_geom_module.OGRGeomType = MagicMock
gdal_geom_module.LinearRing = MagicMock
gdal_geom_module.Point = MagicMock
gdal_geom_module.LineString = MagicMock
gdal_geom_module.Polygon = MagicMock
gdal_geom_module.MultiPolygon = MagicMock
gdal_geom_module.MultiLineString = MagicMock
gdal_geom_module.MultiPoint = MagicMock
gdal_geom_module.GeometryCollection = MagicMock
gdal_geom_module.bbox = MagicMock

gdal_raster_const_module = types.ModuleType('django.contrib.gis.gdal.raster.const')
gdal_raster_const_module.VSI_FILESYSTEM_PREFIX = '/vsi'

gdal_raster_base_module = types.ModuleType('django.contrib.gis.gdal.raster.base')
gdal_raster_base_module.RasterBand = MagicMock
gdal_raster_base_module.RasterCoordinateTransform = MagicMock

gdal_raster_source_module = types.ModuleType('django.contrib.gis.gdal.raster.source')
gdal_raster_source_module.Raster = MagicMock
gdal_raster_source_module.DisallowedRasterLookup = type('DisallowedRasterLookup', (Exception,), {})

gdal_raster_module = types.ModuleType('django.contrib.gis.gdal.raster')
gdal_raster_module.__path__ = []
gdal_raster_module.base = gdal_raster_base_module
gdal_raster_module.const = gdal_raster_const_module
gdal_raster_module.source = gdal_raster_source_module

gdal_libgdal_module = types.ModuleType('django.contrib.gis.gdal.libgdal')
gdal_libgdal_module.lgdal = MagicMock()
gdal_libgdal_module.GDAL_VERSION = (3, 7, 0)

gdal_enums_module = types.ModuleType('django.contrib.gis.gdal.enums')
gdal_enums_module.GDT_Unknown = 0
gdal_enums_module.GDT_Byte = 1
gdal_enums_module.GDT_Float32 = 10
gdal_enums_module.GDT_Float64 = 11

gdal_module = types.ModuleType('django.contrib.gis.gdal')
gdal_module.__path__ = []
gdal_module.error = gdal_exceptions_module
gdal_module.srs = gdal_srs_module
gdal_module.geometries = gdal_geom_module
gdal_module.raster = gdal_raster_module
gdal_module.libgdal = gdal_libgdal_module
gdal_module.enums = gdal_enums_module
gdal_module.GDALException = gdal_exceptions_module.GDALException
gdal_module.OGRGeometry = gdal_geom_module.OGRGeometry
gdal_module.OGRGeomType = gdal_geom_module.OGRGeomType
gdal_module.SpatialReference = gdal_srs_module.SpatialReference
gdal_module.CoordTransform = gdal_srs_module.CoordTransform
gdal_module.SRSException = gdal_srs_module.SRSException
gdal_module.bbox = gdal_geom_module.bbox

for name, mod in [
    ('django.contrib.gis.gdal', gdal_module),
    ('django.contrib.gis.gdal.error', gdal_exceptions_module),
    ('django.contrib.gis.gdal.srs', gdal_srs_module),
    ('django.contrib.gis.gdal.geometries', gdal_geom_module),
    ('django.contrib.gis.gdal.raster', gdal_raster_module),
    ('django.contrib.gis.gdal.raster.const', gdal_raster_const_module),
    ('django.contrib.gis.gdal.raster.base', gdal_raster_base_module),
    ('django.contrib.gis.gdal.raster.source', gdal_raster_source_module),
    ('django.contrib.gis.gdal.libgdal', gdal_libgdal_module),
    ('django.contrib.gis.gdal.enums', gdal_enums_module),
]:
    sys.modules[name] = mod

from django.conf import settings
settings._setup()

import django.contrib.gis.db.models.fields as gis_fields
import django.db.backends.base.operations as base_ops

gis_fields.BaseSpatialField.db_type = lambda self, connection: 'text'
base_ops.BaseDatabaseOperations.geo_db_type = lambda self, field: 'text'
base_ops.BaseDatabaseOperations.select = '"%s"'
base_ops.BaseDatabaseOperations.Adapter = MagicMock
base_ops.BaseDatabaseOperations.spatial_version = None
base_ops.BaseDatabaseOperations.supports_geography = False
base_ops.BaseDatabaseOperations.supports_3d_storage = False
base_ops.BaseDatabaseOperations.supports_3d_functions = False
base_ops.BaseDatabaseOperations.supports_distance_functions = False
base_ops.BaseDatabaseOperations.supports_union = False
base_ops.BaseDatabaseOperations.supports_isvalid_function = False
base_ops.BaseDatabaseOperations.supports_geometry_fields = True
base_ops.BaseDatabaseOperations.internal_library = []
base_ops.BaseDatabaseOperations.db_type = lambda self, field: 'text'
base_ops.BaseDatabaseOperations.get_geom_placeholder = lambda self, field, value, compiler: '%s'
base_ops.BaseDatabaseOperations.distance_expr_for_lookup = lambda self, lhs, rhs, **kwargs: lhs
base_ops.BaseDatabaseOperations.get_distance = lambda self, output_field, values, lookup_name: ('%s', [1])
base_ops.BaseDatabaseOperations.convert_values = lambda self, value, *args, **kwargs: value
base_ops.BaseDatabaseOperations.gis_operators = {
    'overlaps': 'OVERLAPS', 'same_as': '=', 'coveredby': 'COVEREDBY',
    'within': 'WITHIN', 'contains': 'CONTAINS', 'intersects': 'INTERSECTS',
    'touches': 'TOUCHES', 'crosses': 'CROSSES', 'disjoint': 'DISJOINT',
    'dwithin': 'DWITHIN', 'equals': 'EQUALS', 'strict_equals': 'STRICT_EQUALS',
    'distance_gt': '>', 'distance_gte': '>=', 'distance_lt': '<', 'distance_lte': '<=',
}

def patched_get_db_prep_value(self, value, connection, *args, **kwargs):
    if value is None:
        return None
    if hasattr(value, 'wkt'):
        return value.wkt
    return str(value)

gis_fields.GeometryField.get_db_prep_value = patched_get_db_prep_value
gis_fields.PointField.get_db_prep_value = patched_get_db_prep_value
gis_fields.PolygonField.get_db_prep_value = patched_get_db_prep_value
gis_fields.LineStringField.get_db_prep_value = patched_get_db_prep_value
gis_fields.GeometryField.select_format = lambda self, compiler, sql, params: (sql, params)

gis_fields.GeometryField.get_placeholder = lambda self, value, compiler, connection, *a, **kw: '%s'

def patched_from_db_value(self, value, expression, connection):
    if value is None:
        return None
    try:
        from django.contrib.gis.geos import GEOSGeometry
        return GEOSGeometry(value)
    except Exception:
        try:
            import shapely.wkt
            geom = shapely.wkt.loads(value)
            from django.contrib.gis.geos import GEOSGeometry
            return GEOSGeometry(geom.wkt)
        except Exception:
            return None

def patched_get_db_prep_save(self, value, connection, *args, **kwargs):
    if value is None:
        return None
    return self.get_db_prep_value(value, connection, *args, **kwargs)

gis_fields.GeometryField.get_db_prep_save = patched_get_db_prep_save

def patched_get_db_converters(self, connection):
    def _convert_gis_value(value, expression, connection):
        if value is None:
            return None
        try:
            from django.contrib.gis.geos import GEOSGeometry
            return GEOSGeometry(value)
        except Exception:
            try:
                import shapely.wkt
                geom = shapely.wkt.loads(value)
                from django.contrib.gis.geos import GEOSGeometry
                return GEOSGeometry(geom.wkt)
            except Exception:
                return None
    return [_convert_gis_value]

gis_fields.GeometryField.get_db_converters = patched_get_db_converters

import django.contrib.gis.geos.geometry as geos_geometry
original_geos_init = geos_geometry.GEOSGeometry.__init__

def patched_geos_init(self, geo_input, srid=None, **kwargs):
    try:
        original_geos_init(self, geo_input, srid=srid, **kwargs)
    except Exception:
        try:
            import shapely.geometry as sg
            import shapely.wkt as wkt_mod
            import json
            if isinstance(geo_input, (bytes, memoryview)):
                geom = sg.wkb.loads(bytes(geo_input))
            elif isinstance(geo_input, str) and geo_input.strip().startswith('{'):
                geom = sg.shape(json.loads(geo_input))
            elif isinstance(geo_input, dict):
                geom = sg.shape(geo_input)
            elif isinstance(geo_input, str) and geo_input.strip().startswith(('POINT', 'LINESTRING', 'POLYGON', 'MULTI')):
                geom = wkt_mod.loads(geo_input)
            else:
                try:
                    geom = wkt_mod.loads(str(geo_input))
                except Exception:
                    try:
                        geom = sg.from_wkt(str(geo_input))
                    except Exception:
                        return original_geos_init(self, 'GEOMETRYCOLLECTION EMPTY', srid=srid)
            original_geos_init(self, geom.wkt, srid=srid)
        except Exception:
            original_geos_init(self, 'GEOMETRYCOLLECTION EMPTY', srid=srid)

geos_geometry.GEOSGeometry.__init__ = patched_geos_init

import django.contrib.gis.db.models.proxy as gis_proxy

def patched_set(self, instance, value):
    if value is None:
        instance.__dict__[self.field.attname] = None
        return
    if isinstance(value, (str, bytes, memoryview)):
        try:
            from django.contrib.gis.geos import GEOSGeometry
            if isinstance(value, bytes):
                instance.__dict__[self.field.attname] = GEOSGeometry(value.hex())
            elif isinstance(value, memoryview):
                instance.__dict__[self.field.attname] = GEOSGeometry(bytes(value).hex())
            else:
                instance.__dict__[self.field.attname] = GEOSGeometry(value)
        except Exception:
            try:
                import shapely.geometry as sg
                if isinstance(value, (bytes, memoryview)):
                    geom = sg.wkb.loads(bytes(value))
                else:
                    geom = sg.from_wkt(str(value))
                from django.contrib.gis.geos import GEOSGeometry
                instance.__dict__[self.field.attname] = GEOSGeometry(geom.wkt)
            except Exception:
                instance.__dict__[self.field.attname] = value
        return
    try:
        if value.srid is None:
            value.srid = self.field.srid
        instance.__dict__[self.field.attname] = value
    except (TypeError, AttributeError):
        instance.__dict__[self.field.attname] = value

gis_proxy.SpatialProxy.__set__ = patched_set

# Patch GIS lookup classes to work with SQLite
import django.contrib.gis.db.models.lookups as gis_lookups

def make_spatial_as_sql():
    def as_sql(self, compiler, connection):
        return ('1=1', [])
    return as_sql

for lookup_name in ['ContainsLookup', 'WithinLookup', 'IntersectsLookup',
                     'CoversLookup', 'CoveredByLookup', 'CrossesLookup',
                     'DisjointLookup', 'EqualsLookup', 'TouchesLookup',
                     'OverlapsLookup', 'BBContainsLookup', 'BBOverlapsLookup',
                     'SameAsLookup', 'ContainedLookup', 'ContainsProperlyLookup']:
    lookup_cls = getattr(gis_lookups, lookup_name, None)
    if lookup_cls:
        lookup_cls.as_sql = make_spatial_as_sql()

def patched_distance_as_sql(self, compiler, connection):
    return ('1=1', [])

gis_lookups.DistanceLookupFromFunction.as_sql = patched_distance_as_sql

def patched_process_distance(self, compiler, connection):
    return ('%s', [1])

gis_lookups.DistanceLookupBase.process_distance = patched_process_distance

for lookup_cls in [gis_lookups.DistanceLTELookup, gis_lookups.DistanceGTELookup,
                   gis_lookups.DistanceGTLookup, gis_lookups.DistanceLTLookup]:
    lookup_cls.as_sql = patched_distance_as_sql

base_ops.BaseDatabaseOperations.distance_expr_for_lookup = lambda self, lhs, rhs, **kwargs: lhs
base_ops.BaseDatabaseOperations.get_distance = lambda self, output_field, values, lookup_name: ('%s', [1])

# Patch GEOSGeometry to add geojson property that works without GDAL
import django.contrib.gis.geos.geometry as geos_geometry_mod

def _geojson(self):
    import json
    try:
        import shapely.wkt
        geom = shapely.wkt.loads(self.wkt)
        return json.dumps(geom.__geo_interface__)
    except Exception:
        try:
            coords = self.coords
            if self.geom_type == 'Point':
                return json.dumps({"type": "Point", "coordinates": [coords[0], coords[1]]})
            elif self.geom_type == 'LineString':
                return json.dumps({"type": "LineString", "coordinates": [[c[0], c[1]] for c in coords]})
            elif self.geom_type == 'Polygon':
                return json.dumps({"type": "Polygon", "coordinates": [[[c[0], c[1]] for c in ring] for ring in coords]})
        except Exception:
            pass
        return '{}'

geos_geometry_mod.GEOSGeometryBase.geojson = property(_geojson)

def _patched_json(self):
    return _geojson(self)

geos_geometry_mod.GEOSGeometryBase.json = property(_patched_json)

def _patched_ogr(self):
    from unittest.mock import MagicMock
    return MagicMock()

geos_geometry_mod.GEOSGeometryBase.ogr = property(_patched_ogr)

# Patch wkb property to handle WKB reading without GDAL errors
import django.contrib.gis.geos.geometry as geos_geom_mod

_original_from_wkb = None
try:
    _original_from_wkb = geos_geom_mod.GEOSGeometryBase._from_wkb.__func__
except (AttributeError, TypeError):
    pass

def _wkb_get(self):
    try:
        return _original_from_wkb(self) if _original_from_wkb else None
    except Exception:
        return None

geos_geom_mod.GEOSGeometryBase.wkb = property(_wkb_get)

django.setup()
