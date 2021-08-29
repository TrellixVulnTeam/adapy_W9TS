import uuid
from dataclasses import dataclass
from enum import Enum

import numpy as np
from OCC.Core.Tesselator import ShapeTesselator
from OCC.Core.TopoDS import TopoDS_Shape
from pythreejs import (
    BufferAttribute,
    BufferGeometry,
    LineMaterial,
    LineSegments2,
    LineSegmentsGeometry,
    Mesh,
)

from .threejs_utils import create_material


class NORMAL(Enum):
    SERVER_SIDE = 1
    CLIENT_SIDE = 2


@dataclass
class OccToThreejs:
    parallel = True
    compute_normals_mode = NORMAL.SERVER_SIDE
    render_edges = True
    quality = 1.0

    def occ_shape_to_threejs(self, shp: TopoDS_Shape, shape_color, edge_color, transparency, opacity):
        # first, compute the tesselation
        np_vertices, np_faces, np_normals, edges = occ_shape_to_faces(
            shp, self.quality, self.render_edges, self.parallel
        )

        # set geometry properties
        buffer_geometry_properties = {
            "position": BufferAttribute(np_vertices),
            "index": BufferAttribute(np_faces),
        }
        if self.compute_normals_mode == NORMAL.SERVER_SIDE:
            if np_normals.shape != np_vertices.shape:
                raise AssertionError("Wrong number of normals/shapes")
            buffer_geometry_properties["normal"] = BufferAttribute(np_normals)

        # build a BufferGeometry instance
        shape_geometry = BufferGeometry(attributes=buffer_geometry_properties)

        # if the client has to render normals, add the related js instructions
        if self.compute_normals_mode == NORMAL.CLIENT_SIDE:
            shape_geometry.exec_three_obj_method("computeVertexNormals")

        # then a default material
        shp_material = create_material(shape_color, transparent=transparency, opacity=opacity)

        # and to the dict of shapes, to have a mapping between meshes and shapes
        mesh_id = "%s" % uuid.uuid4().hex

        # finally create the mesh
        shape_mesh = Mesh(geometry=shape_geometry, material=shp_material, name=mesh_id)

        # edge rendering, if set to True
        if self.render_edges:
            edge_list = flatten(list(map(explode, edges)))
            lines = LineSegmentsGeometry(positions=edge_list)
            mat = LineMaterial(linewidth=1, color=edge_color)
            edge_lines = LineSegments2(lines, mat, name=mesh_id)
        else:
            edge_lines = None

        return shape_mesh, edge_lines


def explode(edge_list):
    return [[edge_list[i], edge_list[i + 1]] for i in range(len(edge_list) - 1)]


def flatten(nested_dict):
    return [y for x in nested_dict for y in x]


def occ_shape_to_faces(shape, quality=1.0, render_edges=False, parallel=True):
    """

    :param shape:
    :param quality:
    :param render_edges:
    :param parallel:
    :return:
    """
    # first, compute the tesselation
    tess = ShapeTesselator(shape)
    tess.Compute(compute_edges=render_edges, mesh_quality=quality, parallel=parallel)

    # get vertices and normals
    vertices_position = tess.GetVerticesPositionAsTuple()
    number_of_triangles = tess.ObjGetTriangleCount()
    number_of_vertices = len(vertices_position)

    # number of vertices should be a multiple of 3
    if number_of_vertices % 3 != 0:
        raise AssertionError("Wrong number of vertices")
    if number_of_triangles * 9 != number_of_vertices:
        raise AssertionError("Wrong number of triangles")

    # then we build the vertex and faces collections as numpy ndarrays
    np_vertices = np.array(vertices_position, dtype="float32").reshape(int(number_of_vertices / 3), 3)
    # Note: np_faces is just [0, 1, 2, 3, 4, 5, ...], thus arange is used
    np_faces = np.arange(np_vertices.shape[0], dtype="uint32")

    np_normals = np.array(tess.GetNormalsAsTuple(), dtype="float32").reshape(-1, 3)
    edges = list(
        map(
            lambda i_edge: [tess.GetEdgeVertex(i_edge, i_vert) for i_vert in range(tess.ObjEdgeGetVertexCount(i_edge))],
            range(tess.ObjGetEdgeCount()),
        )
    )
    return np_vertices, np_faces, np_normals, edges
