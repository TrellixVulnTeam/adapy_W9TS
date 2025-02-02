from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import ifcopenshell
import ifcopenshell.geom

from ada.base.changes import ChangeAction
from ada.ifc.utils import assembly_to_ifc_file, default_settings, get_unit_type
from ada.ifc.write.write_sections import get_profile_class
from ada.ifc.write.write_user import create_owner_history_from_user

if TYPE_CHECKING:
    from ada import Assembly, Section, User
    from ada.ifc.read.read_ifc import IfcReader
    from ada.ifc.write.write_ifc import IfcWriter


@dataclass
class IfcStore:
    ifc_file_path: pathlib.Path | os.PathLike = None
    assembly: Assembly = None
    settings: ifcopenshell.geom.settings = field(default_factory=default_settings)

    f: ifcopenshell.file = None
    owner_history: ifcopenshell.entity_instance = None
    writer: IfcWriter = None
    reader: IfcReader = None

    def __post_init__(self):
        if self.f is None:
            if self.ifc_file_path is not None:
                self.ifc_file_path = pathlib.Path(self.ifc_file_path)
                if self.ifc_file_path.exists():
                    self.f = ifcopenshell.open(self.ifc_file_path)
            elif self.assembly is not None:
                self.f = assembly_to_ifc_file(self.assembly)

    def update_owner(self, user: User):
        self.owner_history = create_owner_history_from_user(user, self.f)

    def sync(self, include_fem=False):
        from ada.ifc.write.write_ifc import IfcWriter

        self.writer = IfcWriter(self)

        a = self.assembly

        a.consolidate_sections()
        a.consolidate_materials()

        self.update_owner(a.user)

        num_new_spatial_objects = self.writer.sync_spatial_hierarchy(include_fem=include_fem)

        self.writer.sync_sections()
        self.writer.sync_materials()

        num_new_objects = self.writer.sync_added_physical_objects()

        self.writer.sync_mapped_instances()

        num_mod = self.writer.sync_modified_physical_objects()

        self.writer.sync_presentation_layers()

        num_del = self.writer.sync_deleted_physical_objects()

        add_str = f"Added {num_new_objects} objects and {num_new_spatial_objects} spatial elements"
        mod_str = f"Modified {num_mod} objects"
        del_str = f"Deleted {num_del} objects"

        print(f"Sync Complete. {add_str}. {mod_str}. {del_str}")

    def save_to_file(self, filepath: str | os.PathLike):
        with open(filepath, "w") as f:
            f.write(self.f.wrapped_data.to_string())

    def load_ifc_content_from_file(
        self, ifc_file: str | os.PathLike | ifcopenshell.file = None, data_only=False, elements2part=None
    ) -> None:
        from ada.ifc.read.read_ifc import IfcReader

        if self.ifc_file_path is None:
            if ifc_file is None:
                raise ValueError("No ifc file is attached")
            if isinstance(ifc_file, (str, os.PathLike)):
                self.ifc_file_path = ifc_file
                self.f = IfcStore.ifc_obj_from_ifc_file(ifc_file)
            else:
                self.f = ifc_file

        if self.assembly is None:
            raise ValueError("Assembly must be attached before loading IFC content")

        self.reader = IfcReader(self)

        target_units = None
        unit_type = get_unit_type(self.f)

        if unit_type != self.assembly.units:
            target_units = self.assembly.units
            self.assembly.units = unit_type

        if elements2part is None:
            self.reader.load_spatial_hierarchy()

        # Load Materials
        self.reader.load_materials()

        # Load physical elements
        self.reader.load_objects(data_only=data_only, elements2part=elements2part)

        if target_units is not None:
            self.assembly.units = target_units

        self.reader.load_presentation_layers()

        ifc_file_name = "object" if self.ifc_file_path is None else self.ifc_file_path

        for obj in self.assembly.get_all_sections():
            obj.change_type = ChangeAction.NOCHANGE

        for obj in self.assembly.get_all_materials():
            obj.change_type = ChangeAction.NOCHANGE

        for obj in self.assembly.get_all_physical_objects():
            obj.change_type = ChangeAction.NOCHANGE

        for obj in self.assembly.get_all_parts_in_assembly(include_self=True):
            obj.change_type = ChangeAction.NOCHANGE

        print(f'Import of IFC file "{ifc_file_name}" is complete')

    def get_ifc_geom(self, ifc_elem, settings: ifcopenshell.geom.settings):
        return ifcopenshell.geom.create_shape(settings, inst=ifc_elem)

    def get_ifc_geom_iterator(self, settings: ifcopenshell.geom.settings, cpus: int = None):
        import multiprocessing

        products = []
        for x in self.assembly.get_all_physical_objects(pipe_to_segments=True):
            try:
                product = self.f.by_guid(x.guid)
            except RuntimeError as e:
                raise RuntimeError(e)
            products.append(product)
        cpus = multiprocessing.cpu_count() if cpus is None else cpus
        return ifcopenshell.geom.iterator(settings, self.f, cpus, include=products)

    def get_by_guid(self, guid: str) -> ifcopenshell.entity_instance:
        return self.f.by_guid(guid)

    def get_beam_type(self, section: Section, match_description=False) -> ifcopenshell.entity_instance:
        for beam_type in self.f.by_type("IfcBeamType"):
            if section.name == beam_type.Name:
                return beam_type

    def get_profile_def(self, section: Section) -> ifcopenshell.entity_instance:
        profile_class = get_profile_class(section)
        for profile_def in self.f.by_type(profile_class.get_ifc_type()):
            if profile_def.ProfileName == section.name:
                return profile_def

    @staticmethod
    def from_ifc(ifc_file: str | os.PathLike | ifcopenshell.file, make_a_copy=True) -> IfcStore:
        ifc_file_path = None

        if isinstance(ifc_file, (str, os.PathLike)):
            ifc_file_path = ifc_file
            f = IfcStore.ifc_obj_from_ifc_file(ifc_file)
        else:
            if make_a_copy:
                f = IfcStore.copy_ifc_obj(ifc_file)
            else:
                f = ifc_file

        return IfcStore(ifc_file_path=ifc_file_path, f=f)

    @staticmethod
    def ifc_obj_from_ifc_file(ifc_file: str | os.PathLike) -> ifcopenshell.file:
        ifc_file = pathlib.Path(ifc_file).resolve().absolute()
        if ifc_file.exists() is False:
            raise FileNotFoundError(f'Unable to find "{ifc_file}"')
        return ifcopenshell.open(str(ifc_file))

    @staticmethod
    def copy_ifc_obj(ifc_file: ifcopenshell.file) -> ifcopenshell.file:
        return ifcopenshell.file.from_string(ifc_file.wrapped_data.to_string())
