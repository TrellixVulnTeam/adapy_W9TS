from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Tuple, Union

from ada.base.root import Root
from ada.concepts.curves import CurvePoly
from ada.config import Settings
from ada.sections.categories import BaseTypes, SectionCat

if TYPE_CHECKING:
    from ada import Beam
    from ada.fem import FemSection


@dataclass
class Section(Root):
    type: str = None
    id: int = None
    h: float = None
    w_top: float = None
    w_btn: float = None
    t_w: float = None
    t_ftop: float = None
    t_fbtn: float = None
    r: float = None
    wt: float = None
    sec_id: float = None
    sec_str: str = None
    from_str: str = None
    outer_poly = None
    inner_poly = None
    genprops: GeneralProperties = None
    refs = None

    TYPES = BaseTypes

    def __post_init__(self):
        self._ifc_profile = None
        self._ifc_beam_type = None

        if self.from_str is not None:
            from ada.sections.utils import interpret_section_str

            sec, tap = interpret_section_str(self.from_str, units=self.units)
            self.__dict__.update(sec.__dict__)
        elif self.outer_poly:
            self._type = "poly"

    def equal_props(self, other: Section):
        props = ["type", "h", "w_top", "w_btn", "t_w", "t_ftop", "t_fbtn", "r", "wt", "poly_outer", "poly_inner"]
        if self.type == self.TYPES.GENERAL:
            props += ["properties"]

        for propa, propb in zip(self.unique_props(), other.unique_props()):
            if propa != propb:
                return False

        return True

    def unique_props(self):
        props = ["type", "h", "w_top", "w_btn", "t_w", "t_ftop", "t_fbtn", "r", "wt", "poly_outer", "poly_inner"]
        return tuple([getattr(self, p) for p in props])

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

    @r.setter
    def r(self, value: float):
        self._r = value
        self._genprops = None

    @property
    def wt(self) -> float:
        """Wall thickness"""
        return self._wt

    @wt.setter
    def wt(self, value: float):
        self._wt = value
        self._genprops = None

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
        if self._genprops is None:
            from .properties import calculate_general_properties

            self._genprops = calculate_general_properties(self)

        return self._genprops

    def set_units(self, value):
        if self.units == value:
            return

        from ada.core.utils import unit_length_conversion

        scale_factor = unit_length_conversion(self.units, value)

        if self.poly_inner is not None:
            self.poly_inner.scale(scale_factor, Settings.point_tol)

        if self.poly_outer is not None:
            self.poly_outer.scale(scale_factor, Settings.point_tol)

        vals = ["h", "w_top", "w_btn", "t_w", "t_ftop", "t_fbtn", "r", "wt"]

        for key in self.__dict__.keys():
            if self.__dict__[key] is not None:
                if key[1:] in vals:
                    self.__dict__[key] *= scale_factor
        self.units = value

    @property
    def ifc_profile(self):
        if self._ifc_profile is None:
            from ada.ifc.write.write_sections import export_beam_section_profile_def

            self._ifc_profile = export_beam_section_profile_def(self)
        return self._ifc_profile

    @property
    def ifc_beam_type(self):
        if self._ifc_beam_type is None:
            from ada.ifc.write.write_sections import export_ifc_beam_type

            self._ifc_beam_type = export_ifc_beam_type(self)

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

    @property
    def refs(self) -> List[Union[Beam, FemSection]]:
        return self._refs

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
    TOP_FLANGE = "top_fl"
    BTN_FLANGE = "btn_fl"


@dataclass
class GeneralProperties:
    parent: Section = field(default=None, compare=False)
    Ax: float = None
    Ix: float = None
    Iy: float = None
    Iz: float = None
    Iyz: float = None
    Wxmin: float = None
    Wymin: float = None
    Wzmin: float = None
    Shary: float = None
    Sharz: float = None
    Shceny: float = None
    Shcenz: float = None
    Sy: float = None
    Sz: float = None
    Sfy: float = 1
    Sfz: float = 1
    Cy: float = None
    Cz: float = None

    @property
    def modified(self) -> bool:
        """Returns true if attributes are not equal to the calculated properties of the parent section"""
        return self != self.calc_parent_properties()

    def calc_parent_properties(self) -> GeneralProperties:
        """Returns calculated properties based on parent section"""
        from ada.sections.properties import calculate_general_properties

        return calculate_general_properties(self.parent)


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
        sec_type.TPROFILE: profile_builder.tprofiles,
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
