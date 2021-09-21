from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from ada.base.non_phyical_objects import Backend
from ada.concepts.curves import CurvePoly
from ada.concepts.transforms import Placement
from ada.config import Settings
from ada.core.utils import is_parallel, vector_length

from .categories import SectionCat
from .properties import GeneralProperties


class Section(Backend):
    def __init__(
        self,
        name,
        sec_type=None,
        h=None,
        w_top=None,
        w_btn=None,
        t_w=None,
        t_ftop=None,
        t_fbtn=None,
        r=None,
        wt=None,
        sec_id=None,
        parent=None,
        sec_str=None,
        from_str=None,
        outer_poly=None,
        inner_poly=None,
        genprops=None,
        metadata=None,
        units="m",
        ifc_elem=None,
        guid=None,
    ):
        super(Section, self).__init__(name, guid, metadata, units, ifc_elem=ifc_elem)
        self._type = sec_type
        self._h = h
        self._w_top = w_top
        self._w_btn = w_btn
        self._t_w = t_w
        self._t_ftop = t_ftop
        self._t_fbtn = t_fbtn
        self._r = r
        self._wt = wt
        self._id = sec_id
        self._outer_poly = outer_poly
        self._inner_poly = inner_poly
        self._sec_str = sec_str
        self._parent = parent

        self._ifc_profile = None
        self._ifc_beam_type = None

        if ifc_elem is not None:
            props = self._import_from_ifc_profile(ifc_elem)
            self.__dict__.update(props.__dict__)

        if from_str is not None:
            from ada.sections.utils import interpret_section_str

            if units == "m":
                scalef = 0.001
            elif units == "mm":
                scalef = 1.0
            else:
                raise ValueError(f'Unknown units "{units}"')
            sec, tap = interpret_section_str(from_str, scalef, units=units)
            self.__dict__.update(sec.__dict__)
        elif outer_poly:
            self._type = "poly"

        self._genprops = GeneralProperties() if genprops is None else genprops
        self._genprops.edit(parent=self)

    def __eq__(self, other):
        for key, val in self.__dict__.items():
            if "parent" in key or "_ifc" in key or key in ["_sec_id", "_guid"]:
                continue
            oval = other.__dict__[key]
            if oval != val:
                return False

        return True

    def _generate_ifc_section_data(self):
        from ada.ifc.export_beam_sections import export_beam_section

        return export_beam_section(self)

    def _import_from_ifc_profile(self, ifc_elem):
        from ada.ifc.import_beam_section import import_section_from_ifc

        self._ifc_profile = ifc_elem
        return import_section_from_ifc(ifc_elem)

    @property
    def type(self):
        return self._type

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        if type(value) is not int:
            raise ValueError
        self._id = value

    @property
    def h(self):
        return self._h

    @property
    def w_top(self):
        return self._w_top

    @w_top.setter
    def w_top(self, value):
        """Width of top flange"""
        self._w_top = value

    @property
    def w_btn(self):
        """Width of bottom flange"""
        return self._w_btn

    @w_btn.setter
    def w_btn(self, value):
        self._w_btn = value

    @property
    def t_w(self):
        """Thickness of web"""
        return self._t_w

    @property
    def t_ftop(self):
        """Thickness of top flange"""
        return self._t_ftop

    @property
    def t_fbtn(self):
        """Thickness of bottom flange"""
        return self._t_fbtn

    @property
    def r(self) -> float:
        """Radius (Outer)"""
        return self._r

    @property
    def wt(self) -> float:
        """Wall thickness"""
        return self._wt

    @property
    def sec_str(self):
        def s(x):
            return x / 0.001

        if self.type in SectionCat.box + SectionCat.igirders + SectionCat.tprofiles + SectionCat.shs + SectionCat.rhs:
            sec_str = "{}{:g}x{:g}x{:g}x{:g}".format(self.type, s(self.h), s(self.w_top), s(self.t_w), s(self.t_ftop))
        elif self.type in SectionCat.tubular:
            sec_str = "{}{:g}x{:g}".format(self.type, s(self.r), s(self.wt))
        elif self.type in SectionCat.circular:
            sec_str = "{}{:g}".format(self.type, s(self.r))
        elif self.type in SectionCat.angular:
            sec_str = "{}{:g}x{:g}".format(self.type, s(self.h), s(self.t_w))
        elif self.type in SectionCat.iprofiles:
            sec_str = self._sec_str
        elif self.type in SectionCat.channels:
            sec_str = "{}{:g}".format(self.type, s(self.h))
        elif self.type in SectionCat.general:
            sec_str = "{}{}".format(self.type, self.id)
        elif self.type in SectionCat.flatbar:
            sec_str = f"{self.type}{s(self.h)}x{s(self.w_top)}"
        elif self.type == "poly":
            sec_str = "PolyCurve"
        else:
            raise ValueError(f'Section type "{self.type}" has not been given a section str')
        return sec_str.replace(".", "_") if sec_str is not None else None

    @property
    def properties(self) -> GeneralProperties:
        return self._genprops

    @property
    def units(self):
        return self._units

    @units.setter
    def units(self, value):
        if self._units != value:
            from ada.core.utils import unit_length_conversion

            scale_factor = unit_length_conversion(self._units, value)

            if self.poly_inner is not None:
                self.poly_inner.scale(scale_factor, Settings.point_tol)

            if self.poly_outer is not None:
                self.poly_outer.scale(scale_factor, Settings.point_tol)

            vals = ["h", "w_top", "w_btn", "t_w", "t_ftop", "t_fbtn", "r", "wt"]

            for key in self.__dict__.keys():
                if self.__dict__[key] is not None:
                    if key[1:] in vals:
                        self.__dict__[key] *= scale_factor
            self._units = value

    @property
    def ifc_profile(self):
        if self._ifc_profile is None:
            self._ifc_profile, self._ifc_beam_type = self._generate_ifc_section_data()
        return self._ifc_profile

    @property
    def ifc_beam_type(self):
        if self._ifc_beam_type is None:
            self._ifc_profile, self._ifc_beam_type = self._generate_ifc_section_data()
        return self._ifc_beam_type

    @property
    def poly_outer(self) -> CurvePoly:
        return self._outer_poly

    @property
    def poly_inner(self) -> CurvePoly:
        return self._inner_poly

    def get_section_profile(self, is_solid=True) -> SectionProfile:
        return build_section_profile(self, is_solid)

    def _repr_html_(self):
        from IPython.display import display
        from ipywidgets import HBox

        from ada.visualize.renderer_pythreejs import SectionRenderer

        sec_render = SectionRenderer()
        fig, html = sec_render.build_display(self)
        display(HBox([fig, html]))

    def __hash__(self):
        return hash(self.guid)

    def __repr__(self):
        if self.type in SectionCat.circular + SectionCat.tubular:
            return f"Section({self.name}, {self.type}, r: {self.r}, wt: {self.wt})"
        elif self.type in SectionCat.general:
            p = self.properties
            return f"Section({self.name}, {self.type}, Ax: {p.Ax}, Ix: {p.Ix}, Iy: {p.Iy}, Iz: {p.Iz}, Iyz: {p.Iyz})"
        else:
            return (
                f"Section({self.name}, {self.type}, h: {self.h}, w_btn: {self.w_btn}, "
                f"w_top: {self.w_top}, t_fbtn: {self.t_fbtn}, t_ftop: {self.t_ftop}, t_w: {self.t_w})"
            )


class SectionParts:
    WEB = "web"
    TOP_FLANGE = "top_flange"
    BTN_FLANGE = "btn_flange"


@dataclass
class SectionProfile:
    sec: Section
    is_solid: bool
    outer_curve: CurvePoly = None
    inner_curve: CurvePoly = None
    outer_curve_disconnected: List[CurvePoly] = None
    inner_curve_disconnected: List[CurvePoly] = None
    disconnected: bool = None
    shell_thickness_map: List[Tuple[str, float]] = None

    def get_cog_from_two_curves(self, c1: CurvePoly, c2: CurvePoly) -> List[Tuple[np.ndarray, np.ndarray]]:
        from ada.core.utils import normal_to_points_in_plane

        cogs = []
        for l1, l2 in zip(c1.seg_list, c2.seg_list):
            points = [l1.p1, l1.p2, l2.p1, l2.p2]
            normal = normal_to_points_in_plane(points)
            cog = (l1.p1 + l1.p2 + l2.p1 + l2.p2) / 4
            cogs.append((cog, normal))

        return cogs

    def get_thickness_assignments_for_cogs(
        self,
        cogs_n_normals: List[Tuple[Tuple[float], Tuple[float]]],
        placement_1: Placement,
        placement_2: Placement,
        tol=1e-2,
    ):

        if self.disconnected is False:
            ot = [self.outer_curve]
        else:
            ot = self.outer_curve_disconnected

        res_map = []

        for i, curve in enumerate(ot):
            c1 = copy.deepcopy(curve)
            c2 = copy.deepcopy(curve)
            c1.placement = placement_1
            c2.placement = placement_2

            cogs_profile = self.get_cog_from_two_curves(c1, c2)
            res = self.get_coincident_cog(cogs_n_normals, cogs_profile, tol, i, placement_1)

            if res is None:
                raise ValueError("Unable to find coincident COG for ")
            res_map.append(res)

        return res_map

    def get_coincident_cog(self, cogs_and_normals, cogs_profile, tol, index, placement: Placement):
        for c, normal in cogs_and_normals:
            if SectionCat.is_i_profile(self.sec):
                parallel = is_parallel(normal, placement.xdir)
                if parallel:
                    for bm_part, thick in self.shell_thickness_map:
                        if bm_part == SectionParts.WEB:
                            return (bm_part, thick), normal
                # else:
                #     is_flange = is_parallel(normal, placement.ydir)
                #     if is_flange:
                #         cog_vec = placement.origin - np.array(c)
                #         res = np.dot(placement.zdir, cog_vec)
                #         if res < 0:
                #             flange = SectionParts.TOP_FLANGE
                #         else:
                #             flange = SectionParts.BTN_FLANGE
                #
                #         for bm_part, thick in self.shell_thickness_map:
                #             if bm_part == flange:
                #                 return (bm_part, thick), normal

            for c_, normal in cogs_profile:
                vlen = vector_length(np.array(c) - c_)
                if vlen < tol:
                    return self.shell_thickness_map[index], normal
        return None


def build_section_profile(sec: Section, is_solid) -> SectionProfile:
    import ada.sections.profiles as profile_builder

    section_shape_type = SectionCat.get_shape_type(sec)

    if section_shape_type in SectionCat.tubular + SectionCat.circular + SectionCat.general:
        logging.info("Tubular profiles do not need curve representations")
        return SectionProfile(sec, is_solid)

    sec_type = SectionCat.BASETYPES
    build_map = {
        sec_type.ANGULAR: profile_builder.angular,
        sec_type.IPROFILE: profile_builder.iprofiles,
        sec_type.BOX: profile_builder.box,
        sec_type.FLATBAR: profile_builder.flatbar,
        sec_type.CHANNEL: profile_builder.channel,
    }

    section_builder = build_map.get(section_shape_type, None)

    if section_builder is None and sec.poly_outer is None:
        raise ValueError("Currently geometry build is unsupported for profile type {ptype}".format(ptype=sec.type))

    if section_builder is not None:
        section_profile = section_builder(sec, is_solid)
    else:
        section_profile = SectionProfile(sec, outer_curve=sec.poly_outer, is_solid=is_solid, disconnected=False)

    return section_profile
