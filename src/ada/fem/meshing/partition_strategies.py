from typing import TYPE_CHECKING

from ada import Plate

if TYPE_CHECKING:
    from .concepts import GmshData, GmshSession


def partition_object(gmsh_data: "GmshData", gmsh_session: "GmshSession"):
    obj = gmsh_data.obj

    partition_map = {Plate: partition_plate_with_hole}
    partition_tool = partition_map.get(type(obj), None)

    if partition_tool is None:
        raise NotImplementedError(f'Partitioning of "{type(obj)}" is not yet supported')

    partition_tool(gmsh_data, gmsh_session)


def partition_plate_with_hole(model: "GmshData", gmsh_session: "GmshSession"):
    for dim, tag in model.entities:
        gmsh_session.model.mesh.recombine()
        # ents.append(tag)
        # self.model.mesh.set_transfinite_surface(tag)
        gmsh_session.model.mesh.setRecombine(dim, tag)

    # gmsh_session.open_gui()
    #
    # raise NotImplementedError()
