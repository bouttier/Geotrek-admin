import json
import logging

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Point

logger = logging.getLogger(__name__)


class TopologyHelper(object):
    @classmethod
    def deserialize(cls, serialized):
        """
        Topologies can be points or lines. Serialized topologies come from Javascript
        module ``topology_helper.js``.

        Example of linear point topology (snapped with path 1245):

            {"lat":5.0, "lng":10.2, "snap":1245}

        Example of linear serialized topology :

        [
            {"offset":0,"positions":{"0":[0,0.3],"1":[0.2,1]},"paths":[1264,1208]},
            {"offset":0,"positions":{"0":[0.2,1],"5":[0,0.2]},"paths":[1208,1263,678,1265,1266,686]}
        ]

        * Each sub-topology represents a way between markers.
        * Start point is first position of sub-topology.
        * End point is last position of sub-topology.
        * All last positions represents intermediary markers.

        Global strategy is :
        * If has lat/lng return point topology
        * Otherwise, create path aggregations from serialized data.
        ____________________________________________________________________________________________
        Without Dynamic Segmentation :

        Deserialize normally and create a topology from the geojson
        """
        from .models import Path, Topology, PathAggregation
        try:
            return Topology.objects.get(pk=int(serialized))
        except Topology.DoesNotExist:
            raise
        except (TypeError, ValueError):
            pass  # value is not integer, thus should be deserialized
        if not settings.TREKKING_TOPOLOGY_ENABLED:
            return Topology.objects.create(kind='TMP', geom=GEOSGeometry(serialized, srid=settings.API_SRID))
        objdict = serialized
        if isinstance(serialized, str):
            try:
                objdict = json.loads(serialized)
            except ValueError as e:
                raise ValueError("Invalid serialization: %s" % e)

        if objdict and not isinstance(objdict, list):
            lat = objdict.get('lat')
            lng = objdict.get('lng')
            pk = objdict.get('pk')
            kind = objdict.get('kind')
            # Point topology ?
            if lat is not None and lng is not None:
                if pk:
                    try:
                        return Topology.objects.get(pk=int(pk))
                    except (Topology.DoesNotExist, ValueError):
                        pass

                return cls._topologypoint(lng, lat, kind, snap=objdict.get('snap'))
            else:
                objdict = [objdict]

        if not objdict:
            raise ValueError("Invalid serialized topology : empty list found")

        # If pk is still here, the user did not edit it.
        # Return existing topology instead
        pk = objdict[0].get('pk')
        if pk:
            try:
                return Topology.objects.get(pk=int(pk))
            except (Topology.DoesNotExist, ValueError):
                pass

        offset = objdict[0].get('offset', 0.0)
        topology = Topology.objects.create(kind='TMP', offset=offset)
        try:
            counter = 0
            for j, subtopology in enumerate(objdict):
                last_topo = j == len(objdict) - 1
                positions = subtopology.get('positions', {})
                paths = subtopology['paths']
                # Create path aggregations
                aggrs = []
                for i, path in enumerate(paths):
                    last_path = i == len(paths) - 1
                    # Javascript hash keys are parsed as a string
                    idx = str(i)
                    start_position, end_position = positions.get(idx, (0.0, 1.0))
                    path = Path.objects.get(pk=path)
                    aggrs.append(PathAggregation(
                        path=path,
                        topo_object=topology,
                        start_position=start_position,
                        end_position=end_position,
                        order=counter
                    ))
                    if not last_topo and last_path:
                        counter += 1
                        # Intermediary marker.
                        # make sure pos will be [X, X]
                        # [0, X] or [X, 1] or [X, 0] or [1, X] --> X
                        # [0.0, 0.0] --> 0.0  : marker at beginning of path
                        # [1.0, 1.0] --> 1.0  : marker at end of path
                        pos = -1
                        if start_position == end_position:
                            pos = start_position
                        if start_position == 0.0:
                            pos = end_position
                        elif start_position == 1.0:
                            pos = end_position
                        elif end_position == 0.0:
                            pos = start_position
                        elif end_position == 1.0:
                            pos = start_position
                        elif len(paths) == 1:
                            pos = end_position
                        assert pos >= 0, "Invalid position (%s, %s)." % (start_position, end_position)
                        aggrs.append(PathAggregation(
                            path=path,
                            topo_object=topology,
                            start_position=pos,
                            end_position=pos,
                            order=counter
                        ))
                    counter += 1
                PathAggregation.objects.bulk_create(aggrs)
        except (AssertionError, ValueError, KeyError, Path.DoesNotExist) as e:
            raise ValueError("Invalid serialized topology : %s" % e)
        topology.save()
        return topology

    @classmethod
    def _topologypoint(cls, lng, lat, kind=None, snap=None):
        """
        Receives a point (lng, lat) with API_SRID, and returns
        a topology objects with a computed path aggregation.
        """
        from .models import Path
        from .factories import TopologyFactory
        # Find closest path
        point = Point(lng, lat, srid=settings.API_SRID)
        point.transform(settings.SRID)
        if snap is None:
            closest = Path.closest(point)
            position, offset = closest.interpolate(point)
        else:
            closest = Path.objects.get(pk=snap)
            position, offset = closest.interpolate(point)
            offset = 0
        # We can now instantiante a Topology object
        topology = TopologyFactory.create(paths=[(closest, position, position)], kind=kind, offset=offset)
        point = Point(point.x, point.y, srid=settings.SRID)
        topology.geom = point
        topology.save()
        return topology

    @classmethod
    def serialize(cls, topology, with_pk=True):
        if not topology.aggregations.exists():
            # Empty topology
            return ''
        elif topology.ispoint():
            # Point topology
            point = topology.geom.transform(settings.API_SRID, clone=True)
            objdict = dict(kind=topology.kind, lng=point.x, lat=point.y)
            if with_pk:
                objdict['pk'] = topology.pk
            if settings.TREKKING_TOPOLOGY_ENABLED and topology.offset == 0:
                objdict['snap'] = topology.aggregations.all()[0].path.pk
        else:
            # Line topology
            # Fetch properly ordered aggregations
            aggregations = topology.aggregations.select_related('path').all()
            objdict = []
            current = {}
            ipath = 0
            for i, aggr in enumerate(aggregations):
                last = i == len(aggregations) - 1
                intermediary = aggr.start_position == aggr.end_position

                if with_pk:
                    current.setdefault('pk', topology.pk)
                current.setdefault('kind', topology.kind)
                current.setdefault('offset', topology.offset)
                if not intermediary:
                    current.setdefault('paths', []).append(aggr.path.pk)
                    current.setdefault('positions', {})[ipath] = (aggr.start_position, aggr.end_position)
                ipath = ipath + 1

                subtopology_done = 'paths' in current and (intermediary or last)
                if subtopology_done:
                    objdict.append(current)
                    current = {}
                    ipath = 0
        return json.dumps(objdict)
