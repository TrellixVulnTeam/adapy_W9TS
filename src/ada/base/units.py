from enum import Enum


class InvalidUnit(Exception):
    pass


class Units(Enum):
    M = "m"
    MM = "mm"

    @staticmethod
    def is_valid_unit(unit: str):
        return unit.lower() in list([x.value.lower() for x in Units])

    @staticmethod
    def from_str(unit: str):
        units_map = {x.value.lower(): x for x in Units}
        unit_safe = units_map.get(unit.lower())
        if unit_safe is None:
            raise InvalidUnit

    @staticmethod
    def get_scale_factor(from_unit, to_unit):
        scale_map = {(Units.MM, Units.M): 0.001, (Units.M, Units.M): 1.0, (Units.M, Units.MM): 1000.0}
        return scale_map.get((from_unit, to_unit))
