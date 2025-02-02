from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .exceptions import NoIfcAxesAttachedError
from .read_beams import import_ifc_beam
from .read_pipe import import_pipe_segment
from .read_plates import import_ifc_plate
from .read_shapes import import_ifc_shape

if TYPE_CHECKING:
    from ada.ifc.store import IfcStore


def import_physical_ifc_elem(product, name, ifc_store: IfcStore):
    pr_type = product.is_a()

    if pr_type in ["IfcBeamStandardCase", "IfcBeam"]:
        try:
            return import_ifc_beam(product, name, ifc_store)
        except NoIfcAxesAttachedError as e:
            logging.debug(e)
            pass
    if pr_type in ["IfcPlateStandardCase", "IfcPlate"]:
        try:
            return import_ifc_plate(product, name, ifc_store)
        except NoIfcAxesAttachedError as e:
            logging.debug(e)
            pass

    if product.is_a("IfcOpeningElement") is True:
        logging.info(f'skipping opening element "{product}"')
        return None

    if product.is_a() in ("IfcPipeSegment", "IfcPipeFitting"):
        return import_pipe_segment(product, name, ifc_store)

    if product.is_a("IfcPipeFitting"):
        logging.info('"IfcPipeFitting" is not yet added')

    obj = import_ifc_shape(product, name, ifc_store)

    return obj
