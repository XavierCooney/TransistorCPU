import abc
import os
import re
import sys
import typing as typ

from . import compiled


class AssemblyError(abc.ABC, Exception):
    @abc.abstractmethod
    def print_info(self) -> None: pass


class LinkTimeError(AssemblyError):
    def __init__(self, lines: typ.List[str], msg: str) -> None:
        self.lines = lines
        self.msg = msg

    def print_info(self) -> None:
        print("\n !!! Program Error !!!")
        print('\n'.join(self.lines))
        print(f"\n >>> {self.msg}\n")


class ParseError(AssemblyError):
    def __init__(self, msg: str) -> None:
        self.asm_traceback: typ.List[typ.List[str]] = []
        self.registered_parsers: typ.Set['Parser'] = set()
        self.msg = msg

    def add_traceback(self, lines: typ.List[str], parser: 'Parser') -> None:
        self.asm_traceback.append(lines)
        self.registered_parsers.add(parser)

    def print_info(self) -> None:
        print("\n !!! Parsing Error !!!")
        lines = '\n'.join(
            '\n'.join(entry) for entry in self.asm_traceback[::-1]
        )
        print(lines)
        print(f"\n >>> {self.msg}\n")


class ValueNotReadyException(Exception):
    def __init__(self, msg: str, traceback: typ.Optional['ProgramTraceback']):
        self.msg = msg
        self.traceback = traceback


class Value(abc.ABC):
    backtrace: typ.Optional['ProgramTraceback'] = None


class IdentifierValue(Value):
    def __init__(self, contents: str):
        self.contents = contents


class NumericValue(Value):
    @abc.abstractmethod
    def as_word_array(self, asm: 'Assembler') -> typ.List[int]:
        pass

    def as_integer(self, asm: 'Assembler') -> int:
        word_array = self.as_word_array(asm)

        return sum(
            word * 2 ** (6 * (self.num_words - i - 1))
            for i, word in enumerate(word_array)
        )

    num_words: int


class ConstantNumericValue(NumericValue):
    def __init__(self, value: int, num_words: int):
        self.value = value
        self.num_words = num_words

    @staticmethod
    def int_to_words(value: int, num_words: int) -> typ.List[int]:
        words_reversed = []
        val = value
        while val:
            words_reversed.append(val % 64)
            val //= 64

        words_reversed.extend([0] * (num_words - len(words_reversed)))
        if len(words_reversed) != num_words:
            raise ParseError('Number too big')

        return words_reversed[::-1]

    def as_word_array(self, asm: 'Assembler') -> typ.List[int]:
        return self.int_to_words(self.value, self.num_words)


class LabelValue(NumericValue):
    def __init__(self, name: str):
        self.name = name
        self.num_words = 3

    def as_word_array(self, asm: 'Assembler') -> typ.List[int]:
        if self.name not in asm.label_values:
            raise ValueNotReadyException(
                f"Can't find label {self.name}", self.backtrace
            )

        return ConstantNumericValue.int_to_words(
            asm.label_values[self.name], 3
        )


class MakeResultValue(NumericValue):
    def __init__(self, constituents: typ.List[NumericValue]):
        self.constituents = constituents
        self.num_words = sum(
            constituent.num_words for constituent in constituents
        )

    def as_word_array(self, asm: 'Assembler') -> typ.List[int]:
        word_array = []
        for constituent in self.constituents:
            constituent_result = constituent.as_word_array(asm)
            word_array.extend(constituent_result)
        return word_array


class CodeValue(Value):
    def __init__(
        self, lines: typ.List[str], line_mapping: typ.List[int], origin: str,
    ):
        self.lines = lines
        self.line_mapping = line_mapping
        self.origin = origin

        assert len(self.lines) == len(self.line_mapping)


class InstructionMacro:
    def __init__(
        self, name: str, code_block: CodeValue,
        arg_names: typ.List[str], context: 'Context'
    ) -> None:
        self.name = name
        self.code_block = code_block
        self.arg_names = arg_names
        self.context = context

    def execute(
        self, args: typ.List['Value'],
        assembler: 'Assembler', executing_context: 'Context',
        traceback: 'ProgramTraceback'
    ) -> None:
        if len(self.arg_names) != len(args):
            raise ParseError(
                f"Expected {len(self.arg_names)} arg(s), got {len(args)}"
            )

        new_context = Context(self.context)
        for arg_name, arg_val in zip(self.arg_names, args):
            new_context.define_variable(arg_name, arg_val)

        parser = Parser(
            assembler, self.code_block.lines, self.code_block.line_mapping,
            self.code_block.origin, traceback
        )
        parser.parse_program(new_context)


class Context:
    def __init__(self, parent: typ.Optional['Context']):
        self.parent = parent
        self.instruction_macros: typ.Dict[str, InstructionMacro] = {}
        self.variables: typ.Dict[str, Value] = {}

        if self.parent is not None:
            self.last_global_label: str = self.parent.last_global_label
        else:
            self.last_global_label = '_global_start'

    def find_instruction_macro(
        self, name: str
    ) -> typ.Optional[InstructionMacro]:
        if name in self.instruction_macros:
            return self.instruction_macros[name]
        if self.parent is not None:
            return self.parent.find_instruction_macro(name)
        return None

    def find_variable_value(self, name: str) -> typ.Optional[Value]:
        if name in self.variables:
            return self.variables[name]
        if self.parent is not None:
            return self.find_variable_value(name)
        return None

    def define_variable(self, var_name: str, var_value: Value) -> None:
        if var_name in self.variables:
            raise ParseError(f"Redefinition of variable `{var_name}`")

        self.variables[var_name] = var_value

    def define_instruction(self, macro: InstructionMacro) -> None:
        name = macro.name
        if name in self.instruction_macros:
            raise ParseError(f"Redefinition of command `{name}`")

        self.instruction_macros[name] = macro

    def set_variable(self, var_name: str, var_value: Value) -> None:
        if var_name in self.variables:
            self.variables[var_name] = var_value
        else:
            if self.parent is not None:
                self.parent.set_variable(var_name, var_value)
            else:
                raise ParseError(f"Can't set {var_name} variable")


class ProgramTraceback:
    def __init__(
        self, previous: typ.Optional['ProgramTraceback'], lines: typ.List[str]
    ) -> None:
        self.previous = previous
        self.lines = lines

    def print(self) -> None:
        if self.previous is not None:
            self.previous.print()
        print('\n'.join(self.lines + ['']))

    def gather_lines(self, lines: typ.List[str]) -> None:
        if self.previous is not None:
            self.previous.gather_lines(lines)
        lines.extend(self.lines)

    def trigger_error(self, msg: str) -> typ.NoReturn:
        total_lines: typ.List[str] = []
        self.gather_lines(total_lines)
        raise LinkTimeError(total_lines, msg)


class Assembler:
    def __init__(self) -> None:
        self.written_flags: typ.List[typ.Optional[bool]] = [None] * (2 ** 18)
        self.data_values: typ.List[
            typ.Tuple[int, NumericValue, ProgramTraceback]
        ] = []
        self.label_values: typ.Dict[str, int] = {}
        self.ip = 0
        self.primary_filename: typ.Optional[str] = None

    def assemble_file(self, file_name: str) -> None:
        assert self.primary_filename is None
        self.primary_filename = os.path.abspath(file_name)

        with open(file_name) as file:
            source = file.read()
        self.assemble_source(source, f'"{os.path.abspath(file_name)}"')

    def assemble_source(self, source: str, source_origin: str) -> None:
        sanitised = source.replace('\r', '')
        lines = sanitised.split('\n')

        line_mapping = [
            line_index + 1 for line_index in range(len(lines))
        ]
        parser = Parser(self, lines, line_mapping, source_origin, None)

        parser.parse_program(Context(None))

    def declare_label(self, label: str) -> None:
        if label in self.label_values:
            raise ParseError(f'Redeclaration of label {label}!')
        self.label_values[label] = self.ip

    def run_data_command(
        self, arguments: typ.List[Value], traceback: ProgramTraceback
    ) -> None:
        for arg in arguments:
            if not isinstance(arg, NumericValue):
                raise ParseError(f'DATA expects numeric arg, not {type(arg)}')

            num_words = arg.num_words

            start_ip = self.ip

            for word_num in range(num_words):
                if self.written_flags[self.ip]:
                    raise ParseError('DATA rewrite')
                else:
                    self.written_flags[self.ip] = True
                    self.ip += 1
                    assert self.ip < 2**16

            self.data_values.append((start_ip, arg, traceback))

    def link_data(self) -> compiled.CompiledProgram:
        WordListType = typ.List[typ.Optional[compiled.CompiledWord]]
        data: WordListType = [None] * (2 ** 18)

        for value_start, numeric_value, traceback in self.data_values:
            try:
                word_array = numeric_value.as_word_array(self)
            except ValueNotReadyException as err:
                if err.traceback:
                    err.traceback.trigger_error(err.msg)
                else:
                    traceback.trigger_error(err.msg)

            for word_num, word in enumerate(word_array):
                assert data[word_num + value_start] is None
                data[word_num + value_start] = compiled.CompiledWord(
                    word, traceback, True, True, True
                )

        return compiled.CompiledProgram(
            data, self.label_values
        )

    def run_define_command(
        self, args: typ.List[Value], ctx: Context
    ) -> None:
        if len(args) < 1 or not isinstance(args[0], IdentifierValue):
            raise ParseError("Need define type for DEFINE command")

        define_type = args[0].contents.upper()

        if define_type == 'COMMAND':
            if len(args) < 2 or not isinstance(args[1], IdentifierValue):
                raise ParseError("Need instruction name")

            macro_name = args[1].contents
            macro_arg_name_identifiers = args[2:-1]
            arg_names = []

            for arg_identifier in macro_arg_name_identifiers:
                if not isinstance(arg_identifier, IdentifierValue):
                    raise ParseError("Expected argument name")

                arg_name = arg_identifier.contents
                if arg_name in arg_names:
                    raise ParseError(f"Duplicate argument name {arg_name}")
                arg_names.append(arg_name)

            code_block = args[-1]
            if not isinstance(code_block, CodeValue):
                raise ParseError("Expected code block to define instruction")

            macro = InstructionMacro(macro_name, code_block, arg_names, ctx)
            ctx.define_instruction(macro)
        elif define_type == 'VARIABLE':
            if len(args) != 3:
                raise ParseError('Need 3 args for variable definition')

            if not isinstance(args[1], IdentifierValue):
                raise ParseError("Need variable name")
            var_name = args[1].contents

            ctx.define_variable(var_name, args[2])
        else:
            raise ParseError('Unknown define type')

    def run_set_command(self, args: typ.List[Value], ctx: Context) -> None:
        if len(args) < 1 or not isinstance(args[0], IdentifierValue):
            raise ParseError("Need sub-command for SET command")

        set_type = args[0].contents.upper()

        if set_type == 'VARIABLE_VAL':
            if len(args) != 3:
                raise ParseError('Need 3 args for variable val set')

            if not isinstance(args[1], IdentifierValue):
                raise ParseError("Need variable name")
            var_name = args[1].contents

            ctx.set_variable(var_name, args[2])

    def run_include_command(
        self, args: typ.List[Value], ctx: Context,
        traceback: ProgramTraceback
    ) -> None:
        if len(args) != 1 or not isinstance(args[0], IdentifierValue):
            raise ParseError("Need identifier as first arg to include")

        filename = args[0].contents + '.xasm'

        def normalise(directory: str) -> str:
            return os.path.dirname(os.path.realpath(directory))

        lookup_dirs = []
        if self.primary_filename is not None:
            lookup_dirs.append(normalise(self.primary_filename))
        lookup_dirs.append(normalise(__file__))
        lookup_dirs.append(normalise(os.curdir))

        for lookup_dir in lookup_dirs:
            potential_path = os.path.join(lookup_dir, filename)
            if os.path.exists(potential_path):
                file_path = potential_path
                break
        else:
            raise ParseError(f"Can't find include {filename}")

        with open(file_path) as file:
            source = file.read()

        sanitised = source.replace('\r', '')
        lines = sanitised.split('\n')

        line_mapping = [
            line_index + 1 for line_index in range(len(lines))
        ]
        parser = Parser(self, lines, line_mapping, filename, traceback)

        parser.parse_program(ctx)

    def process_command(
        self, command_name: str,
        arguments: typ.List[Value],
        context: Context, traceback: ProgramTraceback
    ) -> None:
        command_name = command_name.upper()

        if command_name == 'DATA':
            self.run_data_command(arguments, traceback)
        elif command_name == 'DEFINE':
            self.run_define_command(arguments, context)
        elif command_name == 'SET':
            self.run_set_command(arguments, context)
        elif command_name == 'ASSERT':
            raise ParseError('TODO: Assert')
        elif command_name == 'INCLUDE':
            self.run_include_command(arguments, context, traceback)
        elif macro_command := context.find_instruction_macro(command_name):
            macro_command.execute(arguments, self, context, traceback)
        else:
            raise ParseError(f'Unknown command {command_name}')


class Parser:
    IDENTIFIER_REGEX = r'[a-zA-Z_][a-zA-Z_0-9=]*'
    VARIABLE_USEAGE_REGEX = r'\$([a-zA-Z_][a-zA-Z_0-9=]*)'
    NUMERIC_REGEX = r'(0b[01]+)|(0x[a-fA-F0-9]+)|([1-9][0-9]*)|0'
    LABEL_REGEX = r':(\.?)([a-zA-Z_][a-zA-Z_0-9=.]*)'

    def __init__(
        self, assembler: Assembler, virtual_lines: typ.List[str],
        virtual_line_mapping: typ.List[int], original_file_name: str,
        parent_traceback: typ.Optional[ProgramTraceback]
    ) -> None:
        self.lines = [
            line + '\n' for line in virtual_lines
        ]
        self.line_num = 0
        self.last_command_line_num = 0
        self.column_num = 0
        self.assembler = assembler

        self.line_mapping = virtual_line_mapping
        self.source_origin = original_file_name
        self.parent_traceback = parent_traceback

    def advance(self, length: int, skip_whitespace: bool = True) -> None:
        self.column_num += length
        assert self.column_num <= len(self.lines[self.line_num])

        if self.column_num == len(self.lines[self.line_num]):
            self.column_num = 0
            self.line_num += 1

        if skip_whitespace and self.line_num < len(self.lines):
            while self.column_num < len(self.lines[self.line_num]):
                char = self.lines[self.line_num][self.column_num]
                if char in ('\t', ' '):  # don't skip newline
                    self.column_num += 1
                else:
                    break

    def rest_of_line(self) -> str:
        return self.lines[self.line_num][self.column_num:]

    def accept(
        self, regex: str, skip_whitespace: bool = True
    ) -> typ.Optional[re.Match[str]]:
        match = re.match(regex, self.rest_of_line())  # TODO: use pos arg

        if match is not None:
            assert match.span(0)[0] == 0
            self.advance(match.span(0)[1], skip_whitespace)

        return match

    def expect(
        self, regex: str,
        skip_whitespace: bool = True
    ) -> re.Match[str]:
        match = self.accept(regex, skip_whitespace)
        if match is not None:
            return match
        else:
            raise ParseError(f'Expected `{regex}`')

    def parse_function_call(self, name: str, context: Context) -> Value:
        args = []
        while True:
            arg = self.parse_arg(context)
            arg.backtrace = self.current_traceback()
            args.append(arg)

            if self.accept(r'\)'):
                break
            else:
                self.expect(',')

        # TODO: handle errors with function execution better
        if name == 'make':
            if len(args) == 0:
                raise ParseError("Need size argument")

            num_words_arg, *rest = args
            if not isinstance(num_words_arg, ConstantNumericValue):
                raise ParseError("Size argument must be a number constant")
            num_words = num_words_arg.value

            constitutents = []
            for value in rest:
                if not isinstance(value, NumericValue):
                    raise ParseError(f"Need numeric value, not {type(value)}")
                constitutents.append(value)

            result = MakeResultValue(constitutents)

            if result.num_words != num_words:
                raise ParseError(
                    f"Needed {num_words} words, got {result.num_words}"
                )

            return result
        else:
            raise ParseError(f"Unknown method {name}")

    def current_traceback(self) -> ProgramTraceback:
        offending_line_contents = self.lines[self.last_command_line_num][:-1]

        traceback = []
        traceback.append(
            f"At {self.source_origin} on line "
            f"{self.line_mapping[self.last_command_line_num]}:"
        )
        traceback.append(f"    {offending_line_contents}")
        traceback.append("    " + "^" * len(offending_line_contents))

        return ProgramTraceback(self.parent_traceback, traceback)

    def parse_arg(self, context: Context) -> Value:
        if m := self.accept(self.IDENTIFIER_REGEX):
            if self.accept(r'\('):
                return self.parse_function_call(m.group(0), context)
            else:
                return IdentifierValue(m.group(0))

        elif m := self.accept(self.NUMERIC_REGEX, False):
            value = int(m.group(0), base=0)
            word_size = 1
            if m_word_size := self.accept(r'_([1-9]+)'):
                word_size = int(m_word_size.group(1))
            self.expect("")
            return ConstantNumericValue(value, word_size)

        elif m := self.accept(self.LABEL_REGEX):
            is_local = bool(m.group(1))
            name = m.group(2)

            if is_local:
                label = f'{context.last_global_label}.{name}'
            else:
                label = name

            return LabelValue(label)

        elif m := self.accept('{'):
            self.accept('\n')
            lines = []
            current_line_components: typ.List[str] = []
            depth = 0  # TODO: do this more sohpisticated wrt comments, etc.
            line_mapping: typ.List[int] = []

            while True:
                line_segment = self.expect('[^\n{}]*').group(0)

                if len(current_line_components) == 0:
                    line_mapping.append(self.line_mapping[self.line_num])

                current_line_components.append(line_segment)

                if m := self.accept('}'):
                    if depth == 0:
                        break
                    else:
                        current_line_components.append('}')
                        depth -= 1
                elif m := self.accept('{'):
                    current_line_components.append('{')
                    depth += 1
                elif self.accept('\n'):
                    if len(current_line_components) == 0:
                        line_mapping.append(self.line_mapping[self.line_num])

                    lines.append(''.join(current_line_components))
                    current_line_components = []

            if len(current_line_components) == 0:
                line_mapping.append(self.line_mapping[self.line_num])
            lines.append(''.join(current_line_components))

            current_line_components = []

            return CodeValue(
                lines, line_mapping, self.source_origin,
            )

        elif m := self.accept(self.VARIABLE_USEAGE_REGEX):
            variable_name = m.group(1)
            var_value = context.find_variable_value(variable_name)

            if var_value is not None:
                return var_value
            else:
                raise ParseError(f"Can't find variable {variable_name}")

        elif m := self.accept(r'\$\$'):
            return ConstantNumericValue(
                self.assembler.ip, 3
            )

        else:
            raise ParseError("Expected argument")

    def parse_command(self, ctx: Context) -> None:
        self.advance(0)
        command_starting_line = self.line_num
        command_name = self.expect(self.IDENTIFIER_REGEX).group(0)
        self.last_command_line_num = command_starting_line

        arguments = []

        while self.rest_of_line() != '\n':
            arguments.append(self.parse_arg(ctx))

            if self.rest_of_line() != '\n':
                self.expect(',')

        try:
            self.assembler.process_command(
                command_name, arguments, ctx, self.current_traceback()
            )
        except ParseError as parse_err:
            self.handle_parse_error(parse_err, True)
            raise

    def accept_label_declaration(self, ctx: Context) -> bool:
        match = self.accept(self.LABEL_REGEX)

        if not match:
            return False

        is_local = bool(match.group(1))
        name = match.group(2)

        if is_local:
            label = f'{ctx.last_global_label}.{name}'
        else:
            ctx.last_global_label = name.split('.', 2)[0]
            label = name

        self.assembler.declare_label(label)

        return True

    def accept_comment(self) -> None:
        self.accept(r'[ \t]*[rR][eE][mM][^\n]*')

    def handle_parse_error(self, error: ParseError, full_line: bool) -> None:
        if self in error.registered_parsers:
            return

        line_num = self.last_command_line_num if full_line else self.line_num

        offending_line_contents = self.lines[line_num][:-1]
        traceback = []
        traceback.append(
            f"At {self.source_origin} on line "
            f"{self.line_mapping[line_num]}:"
        )
        traceback.append(f"    {offending_line_contents}")
        if full_line:
            traceback.append("    " + "^" * len(offending_line_contents))
        else:
            traceback.append("    " + " " * self.column_num + "^")

        error.add_traceback(traceback, self)

    def parse_program(self, ctx: Context) -> None:
        try:
            while self.line_num < len(self.lines):
                self.accept_comment()
                if self.accept(r'\n'):
                    continue

                if not self.accept_label_declaration(ctx):
                    self.parse_command(ctx)

                self.accept_comment()
                self.expect(r'\n')
        except ParseError as parse_err:
            self.handle_parse_error(parse_err, False)
            raise


def main() -> None:
    if len(sys.argv) != 2:
        print("Need filename as argument")
        sys.exit(1)

    filename = sys.argv[1]

    assembler = Assembler()
    try:
        assembler.assemble_file(filename)
        program = assembler.link_data()
        print(" addr | data")
        for i, word in enumerate(program.data):
            if word is not None:
                print(f" {i:4} | {word.value:4}")
    except AssemblyError as err:
        err.print_info()


if __name__ == '__main__':
    main()
