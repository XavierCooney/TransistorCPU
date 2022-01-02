import abc
import enum
import sys
import typing as typ

from asm.assembler import Assembler, AssemblyError

from .emulator import Emulator


class RunState(enum.Enum):
    PAUSED = enum.auto()
    SINGLE_SHOT = enum.auto()
    RUNNING = enum.auto()


class Breakpoint(abc.ABC):
    @abc.abstractmethod
    def is_triggered(self, emu: 'Emulator') -> bool: pass

    @abc.abstractmethod
    def stringify(self, debugger: 'Debugger') -> str: pass


class SimpleBreakpoint(Breakpoint):
    # this is special because we don't know which breakpoint to refer to
    def __init__(self, pc: int):
        self.pc = pc

    def is_triggered(self, emu: 'Emulator') -> bool:
        return emu.program_counter == self.pc

    def stringify(self, debugger: 'Debugger') -> str:
        if self.pc in debugger.emu.compiled_program.address_to_labels:
            labels = debugger.emu.compiled_program.address_to_labels[self.pc]
            label_text = ' (' + ', '.join(labels) + ')'
        else:
            label_text = ''
        return f'simple, {debugger.memory_info(self.pc)}' + label_text


class Debugger:
    def __init__(self, emu: Emulator):
        self.emu = emu
        self.running_state = RunState.PAUSED
        self.last_command = ''
        self.prompted_from_pause = False
        self.pause_on_output = False
        self.breakpoints: typ.List[Breakpoint] = []

        emu.output_handler = self.on_output

    def exit(self) -> typ.NoReturn:
        sys.exit(0)

    def current_global_label(self) -> typ.Optional[str]:
        compiled = self.emu.compiled_program.data[self.emu.program_counter]

        if compiled is not None:
            traceback = compiled.traceback.get_deepst_non_internal()
            return traceback.last_global_label
        else:
            return None

    def decode_address(self, address_string: str) -> typ.Optional[int]:
        parts = address_string.replace(',', ' ').split(' ')
        parts = [part for part in parts if part]

        if len(parts) == 3:
            try:
                as_words = [int(part) for part in parts]
                return self.emu.words_to_int(as_words)
            except (ValueError, AssertionError):
                print("Can't decode multi word address")
                return None

        elif len(address_string) > 0 and address_string[0] == ':':
            label_name = address_string[1:]
            if label_name in self.emu.compiled_program.labels:
                return self.emu.compiled_program.labels[label_name]
            else:
                print("Can't find global label", address_string[1:])
                return None

        elif len(address_string) > 0 and address_string[0] == '.':
            local_suffix = address_string[1:]
            global_prefix = self.current_global_label()

            if global_prefix is None:
                print('No global prefix to decode local label')
                return None
            else:
                label_name = f'{global_prefix}.{local_suffix}'
                if label_name in self.emu.compiled_program.labels:
                    return self.emu.compiled_program.labels[label_name]
                else:
                    print("Can't find local label", label_name)
                    return None

        elif len(parts) == 1:
            try:
                return int(address_string)
            except ValueError:
                print("Can't decode integer address")
                return None

        else:
            print("Don't know how to decode address")

        return None

    def memory_info(self, address: int) -> str:
        as_words = self.emu.int_to_words(address, 3)
        value = self.emu.memory[address]
        return f'<{address}; {as_words} = {value}>'

    def traceback_word(self, address: int, full: bool) -> None:
        compiled_word = self.emu.compiled_program.data[address]

        if compiled_word is not None:
            if full:
                lines: typ.List[str] = ['']
                compiled_word.traceback.gather_lines(lines)
                print('\n'.join(lines))
            else:
                traceback = compiled_word.traceback.get_deepst_non_internal()
                print(f'{traceback.line_origin:30}', end=' ')
                print(traceback.program_line)
        else:
            print(f"No traceback at address {address}")

    def print_current_instruction(self, full_traceback: bool) -> None:
        program_counter = self.emu.program_counter

        print(f'PC = {self.memory_info(program_counter)}\t', end='')
        print(f'A = {self.emu.a_register} ', end='')
        print()
        print(end='\t')

        opcode, *args = [
            self.emu.read_ram_from_pc(offset)
            for offset in range(4)
        ]
        as_full_address = self.emu.words_to_int(args)
        print(f'opcode {opcode} (0b{opcode:06b}) ', end='')

        if opcode == 0b100000:
            print('LOAD_A', self.memory_info(as_full_address))
        elif opcode == 0b110000:
            print('STORE_A', self.memory_info(as_full_address))
        elif opcode == 0b101000:
            address = self.emu.words_to_int(args[:2] + [self.emu.a_register])
            print('LOAD_A_WITH_A', self.memory_info(address))
        elif opcode == 0b010000:
            print('INC_A')
        elif opcode == 0b000010:
            print('OUTPUT_A', args[0])
        elif opcode == 0b001100:
            print('JUMP', self.memory_info(as_full_address))
        elif opcode == 0b001010:
            print('JUMP_NZ', self.memory_info(as_full_address))
        elif opcode == 0b001001:
            print('JUMP_NZ', self.memory_info(as_full_address))
        else:
            print('UNKNOWN INSTRUCTION')

        address_to_label_dict = self.emu.compiled_program.address_to_labels
        # print(address_to_label_dict)
        if program_counter in address_to_label_dict:
            label_prefix = 'Labels   '
            for label in address_to_label_dict[program_counter]:
                print(label_prefix, ':' + label)
                label_prefix = ' ' * len(label_prefix)

        self.traceback_word(program_counter, full_traceback)

    def run_command(self, command: str, args: typ.List[str]) -> None:
        if command in ('s', 'step'):
            self.running_state = RunState.SINGLE_SHOT
        elif command in ('c', 'continue'):
            self.running_state = RunState.RUNNING
        elif command in ('i', 'inspect'):
            address = self.decode_address(' '.join(args))

            if address is not None:
                self.traceback_word(address, True)
                print(self.memory_info(address))
        elif command in ('b', 'breakpoint'):
            address = self.decode_address(' '.join(args))

            if address is not None:
                bp = SimpleBreakpoint(address)
                self.breakpoints.append(bp)
                print('New breakpoint:', bp.stringify(self))
        elif command == '.':
            self.print_current_instruction(full_traceback=True)
        else:
            print('Unknown command', command)

    def prompt(self) -> None:
        if not self.prompted_from_pause:
            self.print_current_instruction(full_traceback=False)

        try:
            command = input(' dbg >> ')
        except EOFError:
            self.exit()

        if command == '':
            if self.last_command == '':
                return
            else:
                command = self.last_command
        else:
            self.last_command = command

        splitted = command.split(' ')
        self.run_command(splitted[0], splitted[1:])

    def on_output(self, data: typ.Union[str, int]) -> None:
        print('Output:', data)
        if self.pause_on_output:
            print('Break due to output')
            self.running_state = RunState.PAUSED

    def run_step(self) -> None:
        self.emu.step()

        if self.emu.is_self_jump():
            print('Break due to halt loop')
            self.running_state = RunState.PAUSED

        for bp in self.breakpoints:
            if bp.is_triggered(self.emu):
                print(f'Break due to [{bp.stringify(self)}]')
                self.running_state = RunState.PAUSED

    def run(self) -> None:
        while True:
            self.prompt()

            self.prompted_from_pause = False
            if self.running_state == RunState.PAUSED:
                self.prompted_from_pause = True
                continue
            elif self.running_state == RunState.SINGLE_SHOT:
                self.run_step()
                self.running_state = RunState.PAUSED
            else:
                try:
                    while self.running_state == RunState.RUNNING:
                        self.run_step()
                except KeyboardInterrupt:
                    print('Break due to ^C')
                    self.running_state = RunState.PAUSED


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Expected 1 arg for xasm path')
        sys.exit(1)

    print("Loading... ")
    filename = sys.argv[1]

    try:
        asm = Assembler()
        asm.assemble_file(filename)
        compiled = asm.link_data()

        emulator = Emulator(compiled, False)
        Debugger(emulator).run()
    except AssemblyError as err:
        err.print_info()
        sys.exit(1)
