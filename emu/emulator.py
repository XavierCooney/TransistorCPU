import string
import typing as typ

from asm.compiled import CompiledProgram

STRING_CHARS = string.ascii_uppercase + string.digits + '\n'
assert len(STRING_CHARS) < 2**6


class Emulator:
    def __init__(self, program: CompiledProgram, verbose: bool):
        self.memory = [0] * 2 ** 18

        self.compiled_program = program
        assert len(program.data) == len(self.memory)
        for address, word in enumerate(program.data):
            if word is None:
                continue
            self.memory[address] = word.value

        self.program_counter = 0
        self.a_register = 0
        self.memory_address_register = 0
        self.input_register = 0
        self.input_ready_flag = 0

        self.verbose = verbose
        self.outputs: typ.List[typ.Union[int, str]] = []
        self.partial_output: typ.List[str] = []

        OutputHandlerType = typ.Callable[[typ.Union[str, int]], None]
        self.output_handler: OutputHandlerType = lambda data: None

    @staticmethod
    def words_to_int(words: typ.List[int]) -> int:
        value = 0
        for word in words:
            assert 0 <= word < 64
            value = value * 64 + word
        return value

    @staticmethod
    def int_to_words(value: int, num_words: int) -> typ.List[int]:
        assert value >= 0

        words_reversed = []
        while value:
            words_reversed.append(value % 64)
            value //= 64
        words_reversed.extend([0] * (num_words - len(words_reversed)))
        assert len(words_reversed) == num_words

        return words_reversed[::-1]

    def read_ram(self, address: int) -> int:
        assert 0 <= address < 2 ** 18

        compiled_word = self.compiled_program.data[address]
        assert compiled_word is not None
        assert compiled_word.for_reading

        return self.memory[address]

    def write_ram(self, address: int, value: int) -> None:
        assert 0 < address <= 2 ** 18

        compiled_word = self.compiled_program.data[address]
        assert compiled_word is not None
        assert compiled_word.for_writing

        # print(f"Writing, {address}, {value}")
        self.memory[address] = value

    def read_ram_from_pc(self, offset: int) -> int:
        assert 0 <= offset < 4
        assert self.program_counter % 4 == 0
        address = self.program_counter + offset

        compiled_word = self.compiled_program.data[address]
        assert compiled_word is not None
        assert compiled_word.for_execution

        return self.read_ram(self.program_counter + offset)

    def check_state(self) -> None:
        assert self.program_counter % 4 == 0
        pass

    def trigger_error_at_current(self, msg: str) -> None:
        word = self.compiled_program.data[self.program_counter]
        if word is None:
            print(f'\n >>> Error at {self.program_counter}')
            raise Exception(msg)
        else:
            word.traceback.trigger_error(msg)

    def perform_output(self, data: typ.Union[str, int]) -> None:
        if self.verbose:
            print(data, end=' ', flush=True)
        self.outputs.append(data)
        self.output_handler(data)

    def step(self) -> None:
        # FETCH
        opcode = self.read_ram_from_pc(0)
        did_jump = False

        if opcode & 0b100000:
            # Memory I/O
            assert opcode in (0b100000, 0b110000, 0b101000)

            hi = self.read_ram_from_pc(1)
            mid = self.read_ram_from_pc(2)

            if opcode & 0b001000:
                low = self.a_register
            else:
                low = self.read_ram_from_pc(3)

            address = self.words_to_int([hi, mid, low])
            if opcode & 0b010000:
                self.write_ram(address, self.a_register)
            else:
                self.a_register = self.read_ram(address)

        elif opcode & 0b010000:
            # ALU Increment
            assert opcode in (0b010000,)
            self.a_register = (self.a_register + 1) % 64

        elif opcode & 0b001000:
            # Jump
            assert opcode in (0b001100, 0b001010, 0b001001)
            skip = False

            if opcode & 0b000010 and self.a_register == 0:
                skip = True
            if opcode & 0b000001 and self.input_ready_flag:
                skip = True

            if not skip:
                hi = self.read_ram_from_pc(1)
                mid = self.read_ram_from_pc(2)
                low = self.read_ram_from_pc(3)
                assert low % 4 == 0

                self.program_counter = self.words_to_int([hi, mid, low])
                did_jump = True
        elif opcode & 0b000010:
            # Output
            assert opcode in (0b000010,)
            output_type = self.read_ram_from_pc(1)

            if output_type == 0:
                assert 0 <= self.a_register < len(STRING_CHARS)
                self.perform_output(STRING_CHARS[self.a_register])
            elif output_type == 1:
                self.perform_output(self.a_register)
            elif output_type == 2:
                self.partial_output.append(str(self.a_register))
            elif output_type == 3:
                self.perform_output(''.join(self.partial_output))
                self.partial_output = []
            else:
                assert False
        elif opcode & 0b000001:
            assert opcode in (0b000001,)
            self.a_register = self.input_register
        else:
            self.trigger_error_at_current(f'Unknown opcode: 0b{opcode:06b}')

        if not did_jump:
            # TODO: handle wraparound
            self.program_counter = self.program_counter + 4

    def is_self_jump(self) -> bool:
        # check if the next instruction is a jump to itself, indicating a halt
        opcode = self.read_ram_from_pc(0)

        if opcode != 0b001100:  # unconditional jump
            return False

        address = self.words_to_int([
            self.read_ram_from_pc(1),
            self.read_ram_from_pc(2),
            self.read_ram_from_pc(3),
        ])

        return address == self.program_counter
