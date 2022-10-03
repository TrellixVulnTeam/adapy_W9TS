from __future__ import annotations

from dataclasses import dataclass, field

from ada.base.root import Root

from .metals import CarbonSteel


def name_check(value: str):
    if value is None or any(x in value for x in [",", ".", "="]):
        raise ValueError("Material name cannot be None or contain special characters")
    return value.strip()


@dataclass
class Material(Root):
    """The base material class. Currently only supports Metals"""

    model: CarbonSteel = CarbonSteel("S355")
    id: int = None
    refs: list[object] = field(default_factory=list)

    def __post_init__(self):
        self.model.parent = self
        self.name = name_check(self.name)

    def __eq__(self, other: Material):
        """Assuming uniqueness of Material Name and parent"""
        for key, val in self.__dict__.items():
            if "parent" in key or key == "_mat_id":
                continue
            if other.__dict__[key] != val:
                return False

        return True

    def __hash__(self):
        return hash(self.guid)

    def _generate_ifc_mat(self):
        from ada.ifc.write.write_material import write_ifc_mat

        return write_ifc_mat(self)

    def set_units(self, value):
        self.model.units = value

    @property
    def ifc_mat(self):
        if self._ifc_mat is None:
            self._ifc_mat = self._generate_ifc_mat()
        return self._ifc_mat

    def __repr__(self):
        return f'Material(Name: "{self.name}" Material Model: "{self.model}'
