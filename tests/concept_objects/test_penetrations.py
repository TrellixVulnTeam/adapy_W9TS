import numpy as np

from ada import (
    Assembly,
    Beam,
    Part,
    PrimBox,
    PrimCyl,
    PrimExtrude,
    PrimRevolve,
    Section,
    User,
)
from ada.config import Settings

test_dir = Settings.test_dir / "penetrations"


def test_mix_extrude():

    bm = Beam("MyBeam", (0, 0, 0), (1.5, 0, 0), Section("myIPE", from_str="IPE400"))
    a = Assembly("Test", user=User("krande")) / [Part("MyPart") / bm]

    h = 0.2
    r = 0.02

    # Polygon Extrusions
    origin = np.array([0.1, 0.1, -0.1])
    normal = np.array([0, -1, 0])
    xdir = np.array([1, 0, 0])
    points = [(0, 0), (0.05, 0.1), (0.1, 0)]
    bm.add_penetration(PrimExtrude("my_pen", points, h, normal, origin, xdir))

    origin = np.array([0.3, 0.1, -0.1])
    points = [(0, 0, r), (0.1, 0, r), (0.05, 0.1, r)]
    bm.add_penetration(PrimExtrude("my_pen3", points, h, normal, origin, xdir))

    origin = np.array([0.5, 0.1, -0.1])
    points = [(0, 0, r), (0.1, 0, r), (0.1, 0.2, r), (0.0, 0.2, r)]
    bm.add_penetration(PrimExtrude("my_pen4", points, h, normal, origin, xdir))

    # Cylinder Extrude
    x = 0.8
    bm.add_penetration(PrimCyl("my_pen5", (x, -0.1, 0), (x, 0.1, 0), 0.1))

    # Box Extrude
    x = 1.0
    bm.add_penetration(PrimBox("my_pen6", (x, -0.1, -0.1), (x + 0.2, 0.1, 0.1)))

    _ = a.to_ifc(test_dir / "penetrations_mix.ifc", file_obj_only=True)


def test_poly_extrude():
    bm = Beam("MyBeam", (0, 0, 0), (2, 0, 0), Section("myIPE", from_str="IPE400"))
    a = Assembly("Test") / [Part("MyPart") / bm]

    h = 0.2
    r = 0.02

    origin = np.array([0.1, 0.1, -0.1])
    normal = np.array([0, -1, 0])
    xdir = np.array([1, 0, 0])

    points = [(0, 0, r), (0.1, 0, r), (0.05, 0.1, r)]
    bm.add_penetration(PrimExtrude("my_pen1", points, h, normal, origin, xdir))

    origin += np.array([0.2, 0, 0])
    points = [(0, 0, r), (0.1, 0, r), (0.1, 0.2, r), (0, 0.2, r)]
    bm.add_penetration(PrimExtrude("my_pen2", points, h, normal, origin, xdir))

    origin += np.array([0.2, 0, 0])
    points = [(0, 0, r), (0.2, 0, r), (0.25, 0.1, r), (0.25, 0.25, r), (0, 0.25, r)]
    bm.add_penetration(PrimExtrude("my_pen3", points, h, normal, origin, xdir))

    origin += np.array([0.4, 0, 0])
    points = [
        (0, 0, r),
        (0.2, 0, r),
        (0.25, 0.1, r),
        (0.5, 0.0, r),
        (0.5, 0.25, r),
        (0, 0.25, r),
    ]
    bm.add_penetration(PrimExtrude("my_pen4", points, h, normal, origin, xdir))
    _ = a.to_ifc(test_dir / "penetrations_poly.ifc", file_obj_only=True)


def test_poly_revolve():
    bm = Beam("MyBeam", (0, 0, 0), (2, 0, 0), Section("myIPE", from_str="IPE400"))
    a = Assembly("Test") / [Part("MyPart") / bm]
    origin = (1.5, 0, 0.05)
    normal = (1, 0, 0)
    xdir = (0, 1, 0)
    rev_angle = 180
    points2d = [(1, 0.0), (1.2, 0.0), (1.1, 0.2)]

    bm.add_penetration(PrimRevolve("my_pen_revolved", points2d, origin, xdir, normal, rev_angle))

    a.to_stp(test_dir / "penetrations_revolve.stp", return_file_obj=True)
    _ = a.to_ifc(test_dir / "penetrations_revolve.ifc", file_obj_only=True)
