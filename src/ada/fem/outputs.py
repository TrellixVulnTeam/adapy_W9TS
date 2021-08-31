from .common import FemBase


class HistOutput(FemBase):
    """

    :param name: Unique History Output Name
    :param fem_set: Set name associated for history output
    :param set_type:
    :param variables:
    :param int_type: Interval type
    :type name: str
    :type set_type: str
    :type variables: list

    """

    default_hist = [
        "ALLAE",
        "ALLCD",
        "ALLDMD",
        "ALLEE",
        "ALLFD",
        "ALLIE",
        "ALLJD",
        "ALLKE",
        "ALLKL",
        "ALLPD",
        "ALLQB",
        "ALLSD",
        "ALLSE",
        "ALLVD",
        "ALLWK",
        "ETOTAL",
    ]
    _valid_types = ["node", "energy", "contact", "connector"]

    def __init__(
        self,
        name,
        fem_set,
        set_type,
        variables,
        int_value=1,
        int_type="frequency",
        metadata=None,
        parent=None,
    ):
        super().__init__(name, metadata, parent)

        if set_type not in self._valid_types:
            raise ValueError(
                f'set_type "{set_type}" is not yet supported. Currently supported types are "{self._valid_types}"'
            )

        self._fem_set = fem_set
        self._set_type = set_type
        self._variables = variables
        self._int_value = int_value
        self._int_type = int_type

    @property
    def type(self):
        return self._set_type

    @property
    def fem_set(self):
        return self._fem_set

    @property
    def variables(self):
        return self._variables

    @property
    def int_type(self):
        return self._int_type

    @property
    def int_value(self):
        return self._int_value


class FieldOutput(FemBase):
    """
    https://abaqus-docs.mit.edu/2017/English/SIMACAEKEYRefMap/simakey-r-output.htm

    :param name:
    :param nodal:
    :param element:
    :param contact:
    :param int_value: Field output step interval. Default is 1
    :param int_type:
    :param metadata:
    :param parent:
    """

    _valid_fstep_type = ["FREQUENCY", "NUMBER INTERVAL"]
    default_no = ["A", "CF", "RF", "U", "V"]
    default_el = ["LE", "PE", "PEEQ", "PEMAG", "S"]
    default_co = ["CSTRESS", "CDISP", "CFORCE", "CSTATUS"]

    def __init__(
        self,
        name,
        nodal=None,
        element=None,
        contact=None,
        int_value=1,
        int_type="frequency",
        metadata=None,
        parent=None,
    ):
        super().__init__(name, metadata, parent)
        self._nodal = FieldOutput.default_no if nodal is None else nodal
        self._element = FieldOutput.default_el if element is None else element
        self._contact = FieldOutput.default_co if contact is None else contact
        self._int_value = int_value
        self._int_type = int_type

    @property
    def nodal(self):
        return self._nodal

    @property
    def element(self):
        return self._element

    @property
    def contact(self):
        return self._contact

    @property
    def int_value(self):
        return self._int_value

    @int_value.setter
    def int_value(self, value):
        if value < 0:
            raise ValueError("The interval or frequency value cannot be less than 0")

        self._int_value = value

    @property
    def int_type(self):
        return self._int_type.upper()

    @int_type.setter
    def int_type(self, value):
        if value.upper() not in FieldOutput._valid_fstep_type:
            raise ValueError(f'Field output step type "{value}" is not supported')
        self._int_type = value.upper()
