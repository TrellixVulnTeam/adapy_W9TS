from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from ada import Beam, CurvePoly, CurveRevolve
from ada.config import Settings
from ada.core.constants import O
from ada.ifc.utils import (
    add_colour,
    convert_bm_jusl_to_ifc,
    create_guid,
    create_ifc_placement,
    create_local_placement,
    ifc_dir,
    ifc_p,
    to_real,
)
from ada.ifc.write.write_curves import write_curve_poly

if TYPE_CHECKING:
    from ifcopenshell import file as ifile

    from ada.ifc.store import IfcStore


def write_ifc_beam(ifc_store: IfcStore, beam: Beam):
    ibw = IfcBeamWriter(ifc_store)
    return ibw.create_ifc_beam(beam)


@dataclass
class IfcBeamWriter:
    ifc_store: IfcStore

    def create_ifc_beam(self, beam: Beam):
        if beam.parent is None:
            raise ValueError("Parent cannot be None for IFC export")

        f = self.ifc_store.f

        owner_history = self.ifc_store.owner_history
        profile = self.ifc_store.get_profile_def(beam.section)

        if isinstance(beam.curve, CurveRevolve):
            axis, body, loc_plac = create_revolved_beam(beam, f, profile)
        elif isinstance(beam.curve, CurvePoly):
            axis, body, loc_plac = create_polyline_beam(beam, f, profile)
        else:
            if beam.curve is not None:
                raise ValueError(f'Unrecognized beam.curve "{type(beam.curve)}"')
            axis, body, loc_plac = extrude_straight_beam(beam, f, profile)

        prod_def_shp = f.create_entity("IfcProductDefinitionShape", None, None, (axis, body))

        ifc_beam = f.create_entity(
            "IfcBeam",
            GlobalId=beam.guid,
            OwnerHistory=owner_history,
            Name=beam.name,
            Description=beam.section.sec_str,
            ObjectType="Beam",
            ObjectPlacement=loc_plac,
            Representation=prod_def_shp,
        )

        found_existing_relationship = False

        beam_type = self.ifc_store.get_beam_type(beam.section)
        if beam_type is None:
            raise ValueError()

        for ifcrel in f.by_type("IfcRelDefinesByType"):
            if ifcrel.RelatingType == beam_type:
                ifcrel.RelatedObjects = tuple([*ifcrel.RelatedObjects, ifc_beam])
                found_existing_relationship = True
                break

        if found_existing_relationship is False:
            f.create_entity(
                "IfcRelDefinesByType",
                GlobalId=create_guid(),
                OwnerHistory=owner_history,
                Name=beam.section.type.value,
                Description=None,
                RelatedObjects=[ifc_beam],
                RelatingType=beam_type,
            )

        self.add_material_assignment(beam, ifc_beam)

        return ifc_beam

    def add_material_assignment(self, beam: Beam, ifc_beam):
        sec = beam.section
        mat = beam.material
        ifc_store = self.ifc_store
        f = ifc_store.f

        ifc_mat_rel = ifc_store.f.by_guid(mat.guid)
        ifc_mat = ifc_mat_rel.RelatingMaterial

        ifc_profile = ifc_store.get_profile_def(beam.section)
        mat_profile = f.createIfcMaterialProfile(
            sec.name, "A material profile", ifc_mat, ifc_profile, None, "LoadBearing"
        )
        mat_profile_set = f.createIfcMaterialProfileSet(sec.name, None, [mat_profile], None)

        mat_usage = f.create_entity("IfcMaterialProfileSetUsage", mat_profile_set, convert_bm_jusl_to_ifc(beam))

        ifc_store.writer.create_rel_associates_material(create_guid(), mat_usage, [ifc_beam])
        ifc_store.writer.associate_elem_with_material(beam.material, ifc_beam)

        return mat_profile_set


def extrude_straight_beam(beam, f: ifile, profile):
    extrude_dir = ifc_dir(f, (0.0, 0.0, 1.0))
    parent = f.by_guid(beam.parent.guid)
    global_placement = create_local_placement(f, relative_to=parent.ObjectPlacement)
    context = f.by_type("IfcGeometricRepresentationContext")[0]
    e1 = (0.0, 0.0, 0.0)

    if Settings.ifc_export.include_ecc and beam.e1 is not None:
        e1 = beam.e1

    profile_e = None
    if beam.taper is not None and beam.section != beam.taper:
        profile_e = f.by_guid(beam.taper.guid)

    # Transform coordinates to local coords
    p1 = tuple([float(x) + float(e1[i]) for i, x in enumerate(beam.n1.p)])
    p2 = p1 + np.array([0, 0, 1]) * beam.length

    p1_ifc = f.create_entity("IfcCartesianPoint", to_real(p1))
    p2_ifc = f.create_entity("IfcCartesianPoint", to_real(p2))

    ifc_polyline = f.create_entity("IfcPolyLine", [p1_ifc, p2_ifc])

    global_origin = f.createIfcCartesianPoint(O)
    ifc_axis2plac3d = f.create_entity("IfcAxis2Placement3D", global_origin, None, None)

    if profile_e is not None:
        extrude_area_solid = f.create_entity(
            "IfcExtrudedAreaSolidTapered", profile, ifc_axis2plac3d, extrude_dir, beam.length, profile_e
        )
    else:
        extrude_area_solid = f.create_entity("IfcExtrudedAreaSolid", profile, ifc_axis2plac3d, extrude_dir, beam.length)

    # Add colour
    if beam.colour is not None:
        add_colour(f, extrude_area_solid, str(beam.colour), beam.colour)

    ax23d = f.create_entity("IfcAxis2Placement3D", p1_ifc, ifc_dir(f, beam.xvec_e), ifc_dir(f, beam.yvec))
    loc_plac = f.create_entity("IfcLocalPlacement", global_placement, ax23d)
    body = f.create_entity("IfcShapeRepresentation", context, "Body", "SweptSolid", [extrude_area_solid])
    axis = f.create_entity("IfcShapeRepresentation", context, "Axis", "Curve3D", [ifc_polyline])
    return body, axis, loc_plac


def create_revolved_beam(beam, f: "ifile", profile):
    context = f.by_type("IfcGeometricRepresentationContext")[0]
    curve: CurveRevolve = beam.curve

    ifc_trim_curve = create_ifc_trimmed_curve(curve, f)
    placement = create_local_placement(f, curve.p1, (0, 0, 1))
    solid = create_ifcrevolveareasolid(f, profile, placement, curve.p1, curve.rot_axis, np.deg2rad(curve.angle))

    axis = f.create_entity("IfcShapeRepresentation", context, "Axis", "Curve3D", [ifc_trim_curve])
    body = f.create_entity("IfcShapeRepresentation", context, "Body", "SweptSolid", [solid])

    return body, axis, placement


def create_ifc_trimmed_curve(curve: CurveRevolve, f: "ifile"):
    loc_plac = create_ifc_placement(f, origin=curve.rot_origin)
    ifc_circle = f.create_entity("IFCCIRCLE", loc_plac, curve.radius)
    param1 = (f.create_entity("IFCPARAMETERVALUE", 0.0), ifc_p(f, curve.p1))
    param2 = (f.create_entity("IFCPARAMETERVALUE", np.deg2rad(curve.angle)), ifc_p(f, curve.p2))
    trim_curve = f.create_entity(
        "IFCTRIMMEDCURVE",
        BasisCurve=ifc_circle,
        Trim1=param1,
        Trim2=param2,
        SenseAgreement=True,
        MasterRepresentation="PARAMETER",
    )
    return trim_curve


def create_ifcrevolveareasolid(f, profile, ifcaxis2placement, origin, revolve_axis, revolve_angle):
    """Creates an IfcExtrudedAreaSolid from a list of points, specified as Python tuples"""
    ifcaxis1dir = f.create_entity("IfcAxis1Placement", ifc_p(f, origin), ifc_dir(f, revolve_axis))
    return f.create_entity("IfcRevolvedAreaSolid", profile, ifcaxis2placement, ifcaxis1dir, revolve_angle)


def create_polyline_beam(beam, f, profile):

    ifc_polyline = write_curve_poly(beam.curve)

    extrude_dir = ifc_dir(f, (0.0, 0.0, 1.0))
    global_placement = create_ifc_placement(f)

    extrude_area_solid = f.create_entity(
        "IfcFixedReferenceSweptAreaSolid", profile, global_placement, ifc_polyline, 0.0, 1.0, extrude_dir
    )
    loc_plac = create_ifc_placement(f)
    return extrude_area_solid, loc_plac, ifc_polyline


def sweep_beam(beam, f, profile, global_placement, extrude_dir):
    ifc_polyline = write_curve_poly(beam.curve)

    extrude_area_solid = f.create_entity(
        "IfcFixedReferenceSweptAreaSolid", profile, global_placement, ifc_polyline, 0.0, 1.0, extrude_dir
    )
    loc_plac = create_ifc_placement(f)
    return extrude_area_solid, loc_plac, ifc_polyline
