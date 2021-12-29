import abc
import os
import itertools
import typing as typ

from asm import assembler

from emu import emulator

ExpectedOutput = typ.List[typ.Union[str, int]]


class SimpleTest(abc.ABC):
    @abc.abstractproperty
    def xasm_file(self) -> str: pass

    @property
    def test_name(self) -> str:
        return self.__class__.__name__

    @abc.abstractproperty
    def expected_output(self) -> ExpectedOutput: pass

    def setup(self, verbose: bool) -> bool:
        self.assembler = assembler.Assembler()
        try:
            self.assembler.assemble_file(os.path.join(
                os.path.dirname(__file__),
                self.xasm_file
            ) + '.xasm')
            program = self.assembler.link_data()
        except assembler.AssemblyError as err:
            print(f"  Failed to assemble on test {self.test_name}")
            err.print_info()
            return False

        self.emulator = emulator.Emulator(program, verbose)
        return True

    def halt_condition(self) -> bool:
        return self.emulator.is_self_jump()

    def run(self, verbose: bool) -> bool:
        print(f" == {self.test_name} == ")
        if not self.setup(verbose):
            return False

        while not self.halt_condition():
            self.emulator.step()
        if verbose:
            print('\n Halted')

        actual_output = self.emulator.outputs
        expected_ouput = self.expected_output

        if actual_output != expected_ouput:
            zipped = list(itertools.zip_longest(actual_output, expected_ouput))
            first_bad_index = [
                actual == expected for actual, expected in zipped
            ].index(False)
            print(f" Discrepancy in output at index {first_bad_index}")
            print(f"     Expected: {zipped[first_bad_index][1]}")
            print(f"       Actual: {zipped[first_bad_index][0]}")
            return False

        return True


class Count1Test(SimpleTest):
    xasm_file = 'count_1'
    test_name = 'count 1'
    expected_output: ExpectedOutput = list(range(64))


class NoOpTest(SimpleTest):
    xasm_file = 'noop'
    test_name = 'noop'
    expected_output: ExpectedOutput = []


class Addition1Test(SimpleTest):
    xasm_file = 'addition_1'
    test_name = 'addition 1'
    expected_output: ExpectedOutput = [11, 35, 54]


class LibAddTest(SimpleTest):
    xasm_file = 'lib_add_1'
    test_name = 'library adder'
    expected_output: ExpectedOutput = [11, 35, 54]


class LibMultiplyTest(SimpleTest):
    xasm_file = 'lib_mult_1'
    test_name = 'library multiplier'
    expected_output: ExpectedOutput = [42, 12, 12]


all_tests = [
    Count1Test(),
    NoOpTest(),
    Addition1Test(),
    LibAddTest(),
    LibMultiplyTest(),
]

VERBOSE = True

if __name__ == '__main__':
    for test in all_tests:
        if not test.run(VERBOSE):
            break
    else:
        print("\t\tSuccess!")
