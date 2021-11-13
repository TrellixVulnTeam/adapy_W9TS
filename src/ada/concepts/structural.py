from __future__ import annotations

import logging
from typing import List, Union

import numpy as np

from ada.base.physical_objects import BackendGeom
from ada.concepts.bounding_box import BoundingBox
from ada.concepts.curves import CurvePoly, CurveRevolve
from ada.concepts.points import Node
from ada.concepts.primitives import PrimBox
from ada.concepts.transforms import Placement
from ada.config import Settings
from ada.core.utils import Counter, roundoff
from ada.core.vector_utils import (
    angle_between,
    calc_yvec,
    calc_zvec,
    unit_vector,
    vector_length,
)
from ada.ifc.utils import create_guid
from ada.materials import Material
from ada.materials.metals import CarbonSteel
from ada.materials.utils import get_material
from ada.sections import Section
from ada.sections.utils import get_section

section_counter = Counter(1)
material_counter = Counter(1)


class Justification:
    NA = "neutral axis"
    TOS = "top of steel"


class Beam(BackendGeom):
    """
    The base Beam object

    :param n1: Start position of beam. List or Node object
    :param n2: End position of beam. List or Node object
    :param sec: Section definition. Str or Section Object
    :param mat: Material. Str or Material object. String: ['S355' & 'S420'] (default is 'S355' if None is parsed)
    :param name: Name of beam
    :param tap: Tapering of beam. Str or Section object
    :param jusl: Justification of Beam centreline
    :param curve: Curve
    """

    JUSL_TYPES = Justification

    def __init__(
        self,
        name,
        n1=None,
        n2=None,
        sec: Union[str, Section] = None,
        mat: Union[str, Material] = None,
        tap: Union[str, Section] = None,
        jusl=JUSL_TYPES.NA,
        up=None,
        angle=0.0,
        curve: Union[CurvePoly, CurveRevolve] = None,
        e1=None,
        e2=None,
        colour=None,
        parent=None,
        metadata=None,
        ifc_geom=None,
        opacity=None,
        units="m",
        ifc_elem=None,
        guid=None,
        placement=Placement(),
    ):
        super().__init__(name, metadata=metadata, units=units, guid=guid, ifc_elem=ifc_elem, placement=placement)
        if curve is not None:
            curve.parent = self
            if type(curve) is CurvePoly:
                n1 = curve.points3d[0]
                n2 = curve.points3d[-1]
            elif type(curve) is CurveRevolve:
                n1 = curve.p1
                n2 = curve.p2
            else:
                raise ValueError(f'Unsupported curve type "{type(curve)}"')

        self.colour = colour
        self._curve = curve
        self._n1 = n1 if type(n1) is Node else Node(n1[:3], units=units)
        self._n2 = n2 if type(n2) is Node else Node(n2[:3], units=units)
        self._jusl = jusl

        self._connected_to = []
        self._connected_end1 = None
        self._connected_end2 = None
        self._tos = None
        self._e1 = e1
        self._e2 = e2
        self._hinge_prop = None

        self._parent = parent
        self._bbox = None

        # Section and Material setup
        self._section, self._taper = get_section(sec)
        self._section.refs.append(self)
        self._taper.refs.append(self)
        self._material = get_material(mat)
        self._material.refs.append(self)

        if tap is not None:
            self._taper, _ = get_section(tap)

        self._section.parent = self
        self._taper.parent = self

        # Define orientations

        xvec = unit_vector(self.n2.p - self.n1.p)
        tol = 1e-3
        zvec = calc_zvec(xvec)
        gup = np.array(zvec)

        if up is None:
            if angle != 0.0 and angle is not None:
                from pyquaternion import Quaternion

                my_quaternion = Quaternion(axis=xvec, degrees=angle)
                rot_mat = my_quaternion.rotation_matrix
                up = np.array([roundoff(x) if abs(x) != 0.0 else 0.0 for x in np.matmul(gup, np.transpose(rot_mat))])
            else:
                up = np.array([roundoff(x) if abs(x) != 0.0 else 0.0 for x in gup])
            yvec = calc_yvec(xvec, up)
        else:
            if (len(up) == 3) is False:
                raise ValueError("Up vector must be length 3")
            if vector_length(xvec - up) < tol:
                raise ValueError("The assigned up vector is too close to your beam direction")
            yvec = calc_yvec(xvec, up)
            # TODO: Fix improper calculation of angle (e.g. xvec = [1,0,0] and up = [0, 1,0] should be 270?
            rad = angle_between(up, yvec)
            angle = np.rad2deg(rad)
            up = np.array(up)

        # lup = np.cross(xvec, yvec)
        self._xvec = xvec
        self._yvec = np.array([roundoff(x) for x in yvec])
        self._up = up
        self._angle = angle

        self._ifc_geom = ifc_geom
        self._opacity = opacity

    def get_outer_points(self):
        from itertools import chain

        from ada.core.vector_utils import local_2_global_nodes

        section_profile = self.section.get_section_profile(False)
        if section_profile.disconnected:
            ot = list(chain.from_iterable([x.points2d for x in section_profile.outer_curve_disconnected]))
        else:
            ot = section_profile.outer_curve.points2d

        yv = self.yvec
        xv = self.xvec
        p1 = self.n1.p
        p2 = self.n2.p

        nodes_p1 = local_2_global_nodes(ot, p1, yv, xv)
        nodes_p2 = local_2_global_nodes(ot, p2, yv, xv)

        return nodes_p1, nodes_p2

    def _generate_ifc_elem(self):
        from ada.ifc.write.write_beams import write_ifc_beam

        return write_ifc_beam(self)

    def calc_con_points(self, point_tol=Settings.point_tol):
        from ada.core.vector_utils import sort_points_by_dist

        a = self.n1.p
        b = self.n2.p
        points = [tuple(con.centre) for con in self.connected_to]

        def is_mem_eccentric(mem, centre):
            is_ecc = False
            end = None
            if point_tol < vector_length(mem.n1.p - centre) < mem.length * 0.9:
                is_ecc = True
                end = mem.n1.p
            if point_tol < vector_length(mem.n2.p - centre) < mem.length * 0.9:
                is_ecc = True
                end = mem.n2.p
            return is_ecc, end

        if len(self.connected_to) == 1:
            con = self.connected_to[0]
            if con.main_mem == self:
                for m in con.beams:
                    if m != self:
                        is_ecc, end = is_mem_eccentric(m, con.centre)
                        if is_ecc:
                            logging.info(f'do something with end "{end}"')
                            points.append(tuple(end))

        midpoints = []
        prev_p = None
        for p in sort_points_by_dist(a, points):
            p = np.array(p)
            bmlen = self.length
            vlena = vector_length(p - a)
            vlenb = vector_length(p - b)

            if prev_p is not None:
                if vector_length(p - prev_p) < point_tol:
                    continue

            if vlena < point_tol:
                self._connected_end1 = self.connected_to[points.index(tuple(p))]
                prev_p = p
                continue

            if vlenb < point_tol:
                self._connected_end2 = self.connected_to[points.index(tuple(p))]
                prev_p = p
                continue

            if vlena > bmlen or vlenb > bmlen:
                prev_p = p
                continue

            midpoints += [p]
            prev_p = p

        return midpoints

    @property
    def units(self):
        return self._units

    @units.setter
    def units(self, value):
        if self._units != value:
            self.n1.units = value
            self.n2.units = value
            self.section.units = value
            self.material.units = value
            for pen in self.penetrations:
                pen.units = value
            self._units = value

    @property
    def section(self) -> Section:
        return self._section

    @section.setter
    def section(self, value):
        self._section = value

    @property
    def taper(self) -> Section:
        return self._taper

    @taper.setter
    def taper(self, value):
        self._taper = value

    @property
    def material(self) -> Material:
        return self._material

    @material.setter
    def material(self, value):
        self._material = value

    @property
    def member_type(self):
        from ada.core.vector_utils import is_parallel

        xvec = self.xvec
        if is_parallel(xvec, [0.0, 0.0, 1.0], tol=1e-1):
            mtype = "Column"
        elif xvec[2] == 0.0:
            mtype = "Girder"
        else:
            mtype = "Brace"

        return mtype

    @property
    def connected_to(self):
        """:rtype: List[ada.concepts.connections.JointBase]"""
        return self._connected_to

    @property
    def connected_end1(self):
        return self._connected_end1

    @property
    def connected_end2(self):
        return self._connected_end2

    @property
    def length(self) -> float:
        """Returns the length of the beam"""
        p1 = self.n1.p
        p2 = self.n2.p

        if self.e1 is not None:
            p1 += self.e1
        if self.e2 is not None:
            p2 += self.e2
        return vector_length(p2 - p1)

    @property
    def jusl(self):
        """Justification line"""
        return self._jusl

    @property
    def ori(self):
        """Get the xvector, yvector and zvector of a given beam"""

        return self.xvec, self.yvec, self.up

    @property
    def xvec(self) -> np.ndarray:
        """Local X-vector"""
        return self._xvec

    @property
    def yvec(self) -> np.ndarray:
        """Local Y-vector"""
        return self._yvec

    @property
    def up(self) -> np.ndarray:
        return self._up

    @property
    def n1(self) -> Node:
        return self._n1

    @n1.setter
    def n1(self, value):
        self._n1 = value

    @property
    def n2(self) -> Node:
        return self._n2

    @n2.setter
    def n2(self, value):
        self._n2 = value

    @property
    def bbox(self) -> BoundingBox:
        """Bounding Box of beam"""
        if self._bbox is None:
            self._bbox = BoundingBox(self)

        return self._bbox

    @property
    def e1(self) -> np.ndarray:
        return self._e1

    @e1.setter
    def e1(self, value):
        self._e1 = np.array(value)

    @property
    def e2(self) -> np.ndarray:
        return self._e2

    @e2.setter
    def e2(self, value):
        self._e2 = np.array(value)

    @property
    def hinge_prop(self):
        """:rtype: ada.fem.elements.HingeProp"""
        return self._hinge_prop

    @hinge_prop.setter
    def hinge_prop(self, value):
        """:type value: ada.fem.elements.HingeProp"""
        value.beam_ref = self
        if value.end1 is not None:
            value.end1.concept_node = self.n1
        if value.end2 is not None:
            value.end2.concept_node = self.n2
        self._hinge_prop = value

    @property
    def opacity(self):
        return self._opacity

    @property
    def curve(self) -> CurvePoly:
        return self._curve

    @property
    def line(self):
        from ada.occ.utils import make_wire_from_points

        # midpoints = self.calc_con_points()
        # points = [self.n1.p]
        # points += midpoints
        # points += [self.n2.p]

        points = [self.n1.p, self.n2.p]

        return make_wire_from_points(points)

    @property
    def shell(self):
        """:rtype: OCC.Core.TopoDS.TopoDS_Shape"""
        from ada.occ.utils import apply_penetrations, create_beam_geom

        geom = apply_penetrations(create_beam_geom(self, False), self.penetrations)

        return geom

    @property
    def solid(self):
        """:rtype: OCC.Core.TopoDS.TopoDS_Shape"""
        from ada.occ.utils import apply_penetrations, create_beam_geom

        geom = apply_penetrations(create_beam_geom(self, True), self.penetrations)

        return geom

    def __hash__(self):
        return hash(self.guid)

    def __eq__(self, other: Beam):
        for key, val in self.__dict__.items():
            if "parent" in key or key in ["_ifc_settings", "_ifc_elem"]:
                continue
            oval = other.__dict__[key]

            if type(val) in (list, tuple, np.ndarray):
                if False in [x == y for x, y in zip(oval, val)]:
                    return False
            try:
                res = oval != val
            except ValueError as e:
                logging.error(e)
                return True

            if res is True:
                return False

        return True

    def __repr__(self):
        p1s = self.n1.p.tolist()
        p2s = self.n2.p.tolist()
        secn = self.section.sec_str
        matn = self.material.name
        return f'Beam("{self.name}", {p1s}, {p2s}, {secn}, {matn})'


class Plate(BackendGeom):
    """
    A plate object. The plate element covers all plate elements. Contains a dictionary with each point of the plate
    described by an id (index) and a Node object.

    :param name: Name of plate
    :param nodes: List of coordinates that make up the plate. Points can be Node, tuple or list
    :param t: Thickness of plate
    :param mat: Material. Can be either Material object or built-in materials ('S420' or 'S355')
    :param placement: Explicitly define origin of plate. If not set
    """

    def __init__(
        self,
        name,
        nodes,
        t,
        mat="S420",
        use3dnodes=False,
        placement=Placement(),
        pl_id=None,
        offset=None,
        colour=None,
        parent=None,
        ifc_geom=None,
        opacity=None,
        metadata=None,
        tol=None,
        units="m",
        ifc_elem=None,
        guid=None,
    ):
        # TODO: Support generation of plate object from IFC elem
        super().__init__(name, guid=guid, metadata=metadata, units=units, ifc_elem=ifc_elem, placement=placement)

        points2d = None
        points3d = None

        if use3dnodes is True:
            points3d = nodes
        else:
            points2d = nodes

        self._pl_id = pl_id
        self._material = mat if isinstance(mat, Material) else Material(mat, mat_model=CarbonSteel(mat))
        self._material.refs.append(self)
        self._t = t

        if tol is None:
            if units == "mm":
                tol = Settings.mmtol
            elif units == "m":
                tol = Settings.mtol
            else:
                raise ValueError(f'Unknown unit "{units}"')

        self._poly = CurvePoly(
            points3d=points3d,
            points2d=points2d,
            normal=self.placement.zdir,
            origin=self.placement.origin,
            xdir=self.placement.xdir,
            tol=tol,
            parent=self,
        )
        self.colour = colour
        self._offset = offset
        self._parent = parent
        self._ifc_geom = ifc_geom
        self._bbox = None
        self._opacity = opacity

    def _generate_ifc_elem(self):
        from ada.ifc.write.write_plate import write_ifc_plate

        return write_ifc_plate(self)

    @property
    def id(self):
        return self._pl_id

    @id.setter
    def id(self, value):
        self._pl_id = value

    @property
    def offset(self):
        return self._offset

    @property
    def t(self):
        """

        :return: Plate thickness
        """
        return self._t

    @property
    def material(self):
        """

        :return:
        :rtype: Material
        """
        return self._material

    @material.setter
    def material(self, value):
        """

        :param value:
        :type value: Material
        """
        self._material = value

    @property
    def n(self):
        """


        :return: Normal vector
        :rtype: np.ndarray
        """
        return self.poly.normal

    @property
    def nodes(self) -> List[Node]:
        return self.poly.nodes

    @property
    def poly(self):
        """:rtype: ada.concepts.curves.CurvePoly"""
        return self._poly

    @property
    def bbox(self):
        """Bounding box of plate"""
        if self._bbox is None:
            self._bbox = self.poly.calc_bbox(self.t)
        return self._bbox

    def volume_cog(self):
        """

        :return: Get a point in the plate's volumetric COG (based on bounding box).
        """

        return np.array(
            [
                (self.bbox[0][0] + self.bbox[0][1]) / 2,
                (self.bbox[1][0] + self.bbox[1][1]) / 2,
                (self.bbox[2][0] + self.bbox[2][1]) / 2,
            ]
        )

    @property
    def metadata(self):
        return self._metadata

    @property
    def line(self):
        return self._poly.wire

    @property
    def shell(self):
        from ada.occ.utils import apply_penetrations

        geom = apply_penetrations(self.poly.face, self.penetrations)

        return geom

    @property
    def solid(self):
        from ada.occ.utils import apply_penetrations

        geom = apply_penetrations(self._poly.make_extruded_solid(self.t), self.penetrations)

        return geom

    @property
    def units(self):
        return self._units

    @units.setter
    def units(self, value):
        if self._units != value:
            from ada.core.utils import unit_length_conversion

            scale_factor = unit_length_conversion(self._units, value)
            tol = Settings.mmtol if value == "mm" else Settings.mtol
            self._t *= scale_factor
            self.poly.scale(scale_factor, tol)
            for pen in self.penetrations:
                pen.units = value
            self.material.units = value
            self._units = value

    def __repr__(self):
        return f"Plate({self.name}, t:{self.t}, {self.material})"


class Wall(BackendGeom):
    _valid_offset_str = ["CENTER", "LEFT", "RIGHT"]
    """
    A wall object representing

    :param points: Points making up wall
    :param height: Height
    :param thickness: Thickness
    :param origin: Origin
    :param offset: Wall offset from points making up the wall centerline. Accepts float | CENTER | LEFT | RIGHT
    """

    def __init__(
        self,
        name,
        points,
        height,
        thickness,
        placement=Placement(),
        offset="CENTER",
        metadata=None,
        colour=None,
        ifc_elem=None,
        units="m",
        guid=None,
    ):
        super().__init__(name, guid=guid, metadata=metadata, units=units, ifc_elem=ifc_elem)

        if ifc_elem is not None:
            self._import_from_ifc(ifc_elem)

        self._name = name
        self.placement = placement
        self.colour = colour
        new_points = []
        for p in points:
            np_ = [float(c) for c in p]
            if len(np_) == 2:
                np_ += [0.0]
            new_points.append(tuple(np_))
        self._points = new_points
        self._segments = list(zip(self._points[:-1], self.points[1:]))
        self._height = height
        self._thickness = thickness
        self._openings = []
        self._doors = []
        self._inserts = []
        if type(offset) is str:
            if offset not in Wall._valid_offset_str:
                raise ValueError(f'Unknown string input "{offset}" for offset')
            if offset == "CENTER":
                self._offset = 0.0
            elif offset == "LEFT":
                self._offset = -self._thickness / 2
            else:  # offset = RIGHT
                self._offset = self._thickness / 2
        else:
            if type(offset) not in (float, int):
                raise ValueError("Offset can only be string or float, int")
            self._offset = offset

    def add_insert(self, insert, wall_segment: int, off_x, off_z):
        """

        :param insert:
        :param wall_segment:
        :param off_x:
        :param off_z:
        :type insert: ada.param_models.basic_structural_components.Window
        :return:
        """
        from OCC.Extend.ShapeFactory import get_oriented_boundingbox

        xvec, yvec, zvec = self.get_segment_props(wall_segment)
        p1, p2 = self._segments[wall_segment]

        start = p1 + yvec * (self._thickness / 2 + self.offset) + xvec * off_x + zvec * off_z
        insert._depth = self._thickness
        insert.placement = Placement(origin=start, xdir=xvec, ydir=zvec, zdir=yvec)
        insert.build_geom()

        frame = insert.shapes[0]
        center, dim, oobb_shp = get_oriented_boundingbox(frame.geom)
        x, y, z = center.X(), center.Y(), center.Z()
        dx, dy, dz = dim[0], dim[1], dim[2]

        x0 = x - abs(dx / 2)
        y0 = y - abs(dy / 2)
        z0 = z - abs(dz / 2)

        x1 = x + abs(dx / 2)
        y1 = y + abs(dy / 2)
        z1 = z + abs(dz / 2)

        self._inserts.append(insert)
        self._openings.append([wall_segment, insert, (x0, y0, z0), (x1, y1, z1)])

        tol = 0.4
        wi = insert

        p1 = wi.placement.origin - yvec * (wi.depth / 2 + tol)
        p2 = wi.placement.origin + yvec * (wi.depth / 2 + tol) + xvec * wi.width + zvec * wi.height

        self._penetrations.append(PrimBox("my_pen", p1, p2))

    def get_segment_props(self, wall_segment):
        """

        :param wall_segment:
        :return:
        """
        if wall_segment > len(self._segments):
            raise ValueError(f"Wall segment id should be equal or less than {len(self._segments)}")
        p1, p2 = self._segments[wall_segment]
        xvec = unit_vector(np.array(p2) - np.array(p1))
        zvec = np.array([0, 0, 1])
        yvec = unit_vector(np.cross(zvec, xvec))

        return xvec, yvec, zvec

    def _import_from_ifc(self, ifc_elem):
        raise NotImplementedError("Import of IfcWall is not yet supported")

    def _generate_ifc_elem(self):
        from ada.ifc.write.write_wall import wall_to_ifc

        return wall_to_ifc(self)

    @property
    def inserts(self):
        return self._inserts

    @property
    def height(self):
        return self._height

    @property
    def thickness(self):
        return self._thickness

    @property
    def placement(self) -> Placement:
        return self._placement

    @placement.setter
    def placement(self, value: Placement):
        self._placement = value

    @property
    def points(self):
        return self._points

    @property
    def offset(self):
        """

        :return:
        :rtype: float
        """
        return self._offset

    @property
    def extrusion_area(self):
        from ada.core.vector_utils import intersect_calc, is_parallel

        area_points = []
        vpo = [np.array(p) for p in self.points]
        p2 = None
        yvec = None
        prev_xvec = None
        prev_yvec = None
        zvec = np.array([0, 0, 1])
        # Inner line
        for p1, p2 in zip(vpo[:-1], vpo[1:]):
            xvec = p2 - p1
            yvec = unit_vector(np.cross(zvec, xvec))
            new_point = p1 + yvec * (self._thickness / 2) + yvec * self.offset
            if prev_xvec is not None:
                if is_parallel(xvec, prev_xvec) is False:
                    prev_p = area_points[-1]
                    # next_point = p2 + yvec * (self._thickness / 2) + yvec * self.offset
                    # c_p = prev_yvec * (self._thickness / 2) + prev_yvec * self.offset
                    AB = prev_xvec
                    CD = xvec
                    s, t = intersect_calc(prev_p, new_point, AB, CD)
                    sAB = prev_p + s * AB
                    new_point = sAB
            area_points.append(new_point)
            prev_xvec = xvec
            prev_yvec = yvec

        # Add last point
        area_points.append((p2 + yvec * (self._thickness / 2) + yvec * self.offset))
        area_points.append((p2 - yvec * (self._thickness / 2) + yvec * self.offset))

        reverse_points = []
        # Outer line
        prev_xvec = None
        prev_yvec = None
        for p1, p2 in zip(vpo[:-1], vpo[1:]):
            xvec = p2 - p1
            yvec = unit_vector(np.cross(xvec, np.array([0, 0, 1])))
            new_point = p1 - yvec * (self._thickness / 2) + yvec * self.offset
            if prev_xvec is not None:
                if is_parallel(xvec, prev_xvec) is False:
                    prev_p = reverse_points[-1]
                    c_p = prev_yvec * (self._thickness / 2) - prev_yvec * self.offset
                    new_point -= c_p
            reverse_points.append(new_point)
            prev_xvec = xvec
            prev_yvec = yvec

        reverse_points.reverse()
        area_points += reverse_points

        new_points = []
        for p in area_points:
            new_points.append(tuple([float(c) for c in p]))

        return new_points

    @property
    def openings_extrusions(self):
        from ada.concepts.levels import Part

        op_extrudes = []
        if self.units == "m":
            tol = 0.4
        else:
            tol = 400
        for op in self._openings:
            ws, wi, mi, ma = op
            xvec, yvec, zvec = self.get_segment_props(ws)
            assert issubclass(type(wi), Part)
            p1 = wi.placement.origin - yvec * (wi.depth / 2 + tol)
            p2 = p1 + yvec * (wi.depth + tol * 2)
            p3 = p2 + xvec * wi.width
            p4 = p3 - yvec * (wi.depth + tol * 2)
            op_extrudes.append([p1.tolist(), p2.tolist(), p3.tolist(), p4.tolist(), p1.tolist()])
        return op_extrudes

    @property
    def metadata(self):
        return self._metadata

    @property
    def shell(self):
        poly = CurvePoly(points3d=self.extrusion_area, parent=self)
        return poly.face

    @property
    def solid(self):
        from ada.occ.utils import apply_penetrations

        poly = CurvePoly(points3d=self.extrusion_area, parent=self)

        geom = apply_penetrations(poly.make_extruded_solid(self.height), self.penetrations)

        return geom

    @property
    def units(self):
        return self._units

    @units.setter
    def units(self, value):
        if value != self._units:
            from ada.core.utils import unit_length_conversion

            scale_factor = unit_length_conversion(self._units, value)
            self._height *= scale_factor
            self._thickness *= scale_factor
            self._offset *= scale_factor
            self.placement.origin = np.array([x * scale_factor for x in self.placement.origin])
            self._points = [tuple([x * scale_factor for x in p]) for p in self.points]
            self._segments = list(zip(self._points[:-1], self.points[1:]))
            for pen in self._penetrations:
                pen.units = value
            for opening in self._openings:
                opening[2] = tuple([x * scale_factor for x in opening[2]])
                opening[3] = tuple([x * scale_factor for x in opening[3]])

            for insert in self._inserts:
                insert.units = value

            self._units = value

    def __repr__(self):
        return f"Wall({self.name})"


def get_bm_section_curve(bm: Beam, origin=None) -> CurvePoly:
    origin = origin if origin is not None else bm.n1.p
    section_profile = bm.section.get_section_profile(True)
    points2d = section_profile.outer_curve.points2d
    return CurvePoly(points2d=points2d, origin=origin, xdir=bm.yvec, normal=bm.xvec, parent=bm.parent)


def make_ig_cutplanes(bm: Beam):
    from ..fem.meshing.concepts import CutPlane

    bm1_sec_curve = get_bm_section_curve(bm)
    minz = min([x[2] for x in bm1_sec_curve.points3d])
    maxz = max([x[2] for x in bm1_sec_curve.points3d])
    pmin, pmax = bm.bbox.p1, bm.bbox.p2
    dx, dy, dz = (np.array(pmax) - np.array(pmin)) * 1.3
    x, y, _ = pmin
    cut1 = CutPlane((x, y, minz + bm.section.t_fbtn), dx=dx, dy=dy)
    cut2 = CutPlane((x, y, maxz - bm.section.t_fbtn), dx=dx, dy=dy)
    return [cut1, cut2]
