from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ada.concepts.transforms import Placement
from ada.core.constants import color_map as _cmap

from .root import Root

if TYPE_CHECKING:
    from ada import FEM, Penetration
    from ada.fem import Elem
    from ada.fem.meshing import GmshOptions
    from ada.visualize.renderer_pythreejs import MyRenderer


@dataclass
class Geometry(Root):
    """The backend of all physical components (Beam, Plate, etc.) or aggregate of components (Part, Assembly)"""

    placement: Placement = Placement()
    colour_str: str = None
    colour: tuple = None
    opacity: float = 1.0
    penetrations: list[Penetration] = field(default_factory=list)
    elem_refs: list[Elem] = field(default_factory=list)

    _renderer: MyRenderer = None

    def __post_init__(self):
        self.placement.parent = self

    def to_fem_obj(
        self,
        mesh_size,
        geom_repr,
        options: GmshOptions = None,
        silent=True,
        use_quads=False,
        use_hex=False,
        name="AdaFEM",
        interactive=False,
    ) -> FEM:
        from ada.fem.meshing import GmshOptions, GmshSession

        options = GmshOptions(Mesh_Algorithm=8) if options is None else options
        with GmshSession(silent=silent, options=options) as gs:
            gs.add_obj(self, geom_repr=geom_repr.upper())
            gs.mesh(mesh_size, use_quads=use_quads, use_hex=use_hex)
            if interactive:
                gs.open_gui()
            return gs.get_fem(name)

    def to_fem(
        self,
        mesh_size,
        geom_repr,
        name: str,
        fem_format: str,
        options: GmshOptions = None,
        silent=True,
        use_quads=False,
        use_hex=False,
        return_assembly=False,
        **kwargs,
    ):
        from ada import Assembly, Part

        p = Part(name)
        p.fem = self.to_fem_obj(mesh_size, geom_repr, options, silent, use_quads, use_hex, name)
        a = Assembly() / (p / self)
        if return_assembly:
            return a
        a.to_fem(name, fem_format, **kwargs)

    def to_stp(
        self, destination_file, geom_repr=None, schema="AP242", silent=False, fuse_piping=False, return_file_obj=False
    ):
        from ada.fem.shapes import ElemType
        from ada.occ.writer import StepExporter

        destination_file = pathlib.Path(destination_file).resolve().absolute()

        geom_repr = ElemType.SOLID if geom_repr is None else geom_repr
        step_export = StepExporter(schema)
        step_export.add_to_step_writer(self, geom_repr, fuse_piping=fuse_piping)
        return step_export.write_to_file(destination_file, silent, return_file_obj=return_file_obj)

    def render_locally(
        self, addr="localhost", server_port=8080, open_webbrowser=False, render_engine="threejs", resolution=(1800, 900)
    ):
        from OCC.Display.WebGl.simple_server import start_server

        from ada.visualize.renderer_pythreejs import MyRenderer

        if render_engine == "xdom":
            from OCC.Display.WebGl import x3dom_renderer

            my_renderer = x3dom_renderer.X3DomRenderer()
            # TODO: Find similarities in build processing as done for THREE.js (tesselate geom etc..).
            # my_renderer.DisplayShape(shape.profile_curve_outer.wire)
            # my_renderer.DisplayShape(shape.sweep_curve.wire)
            # my_renderer.DisplayShape(shape.geom)
            my_renderer.render()
        else:  # Assume THREEJS
            from ipywidgets.embed import embed_minimal_html

            _path = pathlib.Path("temp/index.html").resolve().absolute()

            renderer = MyRenderer(resolution)
            renderer.DisplayObj(self)
            renderer.build_display()

            os.makedirs(_path.parent, exist_ok=True)
            embed_minimal_html(_path, views=renderer.renderer, title="Pythreejs Viewer")
            start_server(addr, server_port, str(_path.parent), open_webbrowser)

    def get_render_snippet(self, view_size=None):
        """Return the html snippet containing threejs renderer"""
        from ipywidgets.embed import embed_snippet

        from ada.visualize.renderer_pythreejs import MyRenderer

        renderer = MyRenderer()
        renderer.DisplayObj(self)
        renderer.build_display()

        return embed_snippet(renderer.renderer)

    @property
    def colour_norm(self):
        if self.colour is None:
            if self.colour_str is None:
                self.colour_str = "white"

            self.colour = _cmap[self.colour_str.lower()]

        return [x / 255 for x in self.colour] if any(i > 1 for i in self.colour) else self.colour

    @property
    def colour_webgl(self):
        from OCC.Display.WebGl.jupyter_renderer import format_color

        if self.colour is None:
            return None
        if self.colour[0] == -1 and self.colour[1] == -1 and self.colour[2] == -1:
            return None

        if self.colour[0] <= 1.0:
            colour = [int(x * 255) for x in self.colour]
        else:
            colour = [int(x) for x in self.colour]

        colour_formatted = format_color(*colour)
        return colour_formatted

    @property
    def transparent(self):
        return False if self.opacity == 1.0 else True

    def _repr_html_(self):
        from ada.config import Settings

        if Settings.use_new_visualize_api is True:
            self._viz.objects = []
            self._viz.add_obj(self)
            self._viz.display(return_viewer=False)
            return ""

        from IPython.display import display
        from ipywidgets import HBox, VBox

        from ada.visualize.renderer_pythreejs import MyRenderer

        renderer = MyRenderer()

        renderer.DisplayObj(self)
        renderer.build_display()
        self._renderer = renderer
        display(HBox([VBox([HBox(renderer.controls), renderer.renderer]), renderer.html]))
        return ""
