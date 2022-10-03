from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from .units import Units

if TYPE_CHECKING:
    from ada import Assembly, Part


class ChangeAction(Enum):
    ADDED = "ADDED"
    DELETED = "DELETED"
    MODIFIED = "MODIFIED"
    NOCHANGE = "NOCHANGE"
    NOTDEFINED = "NOTDEFINED"


@dataclass
class IfcExportOptions:
    export_props: bool = field(default=True)
    import_props: bool = field(default=True)


@dataclass
class Root:
    name: str
    guid: str
    units: Units
    metadata: dict
    change_type: ChangeAction
    parent: Part | Assembly
    UNITS: Units

    def get_assembly(self) -> Assembly | Part:
        from ada import Assembly

        for ancestor in self.get_ancestors():
            if isinstance(ancestor, Assembly):
                return ancestor
        logging.info("No Assembly found in ancestry. Returning self")
        return self

    def get_ancestors(self) -> list[Part | Assembly]:
        ancestry = [self]
        current = self
        while current.parent is not None:
            ancestry.append(current.parent)
            current = current.parent
        return ancestry

    def remove(self):
        """Remove this element/part from assembly/part"""
        ...
        from ada import Beam, Part, Plate, Shape

        if self.parent is None:
            logging.error(f"Unable to delete {self.name} as it does not have a parent")
            return

        # if self._ifc_elem is not None:
        #     a = self.parent.get_assembly()
        # f = a.ifc_file
        # This returns results in a failure error
        # f.remove(self.ifc_elem)

        if type(self) is Part:
            self.parent.parts.pop(self.name)
        elif issubclass(type(self), Shape):
            self.parent.shapes.pop(self.parent.shapes.index(self))
        elif type(self) is Beam:
            self.parent.beams.remove(self)
        elif isinstance(self, Plate):
            self.parent.plates.remove(self)
        else:
            raise NotImplementedError()
