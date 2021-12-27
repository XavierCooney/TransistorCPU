import typing as typ

from . import assembler


class CompiledWord:
    def __init__(
        self, value: int, traceback: 'assembler.ProgramTraceback',
        for_execution: bool, for_reading: bool, for_writing: bool
    ):
        assert 0 <= value < 64
        self.value = value
        self.traceback = traceback

        self.for_execution = for_execution
        self.for_reading = for_reading
        self.for_writing = for_writing


class CompiledProgram:
    def __init__(
        self, data: typ.List[typ.Optional[CompiledWord]],
        labels: typ.Dict[str, int]
    ):
        self.data = data
        self.labels = labels

        self.address_to_labels: typ.Dict[int, typ.List[str]] = {}
        for label, address in self.labels.items():
            if address not in self.address_to_labels:
                self.address_to_labels[address] = []
            self.address_to_labels[address].append(label)
