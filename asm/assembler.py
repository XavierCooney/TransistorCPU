import abc
import os
import re
import sys
import typing as typ


class ParseError(Exception):
    def __init__(self, msg: str) -> None:
        self.asm_traceback: typ.List[typ.List[str]] = []
        self.registered_parsers: typ.Set['Parser'] = set()
        self.msg = msg

    def add_traceback(self, lines: typ.List[str], parser: 'Parser') -> None:
        self.asm_traceback.append(lines)
        self.registered_parsers.add(parser)

    def print_info(self) -> None:
        print("\n !!! Programming Error !!!")
        lines = '\n'.join(
            '\n'.join(entry) for entry in self.asm_traceback[::-1]
        )
        print(lines)
        print(f"\n >>> {self.msg}\n")


class Value(abc.ABC):
    pass


class IdentifierValue(Value):
    def __init__(self, contents: str):
        self.contents = contents


class NumericValue(Value):
    @abc.abstractmethod
    def as_word_array(self, asm: 'Assembler') -> typ.Optional[typ.List[int]]:
        pass

    def as_integer(self, asm: 'Assembler') -> typ.Optional[int]:
        word_array = self.as_word_array(asm)
        if word_array is None:
            return None

        return sum(
            word * 2 ** (6 * (self.num_words - i - 1))
            for i, word in enumerate(word_array)
        )

    num_words: int


class ConstantNumericValue(NumericValue):
    num_words: int

    def __init__(self, value: int, num_words: int):
        self.value = value
        self.num_words = num_words

    def as_word_array(self, asm: 'Assembler') -> typ.Optional[typ.List[int]]:
        words_reversed = []
        val = self.value
        while val:
            words_reversed.append(val % 64)
            val //= 64

        words_reversed.extend([0] * (self.num_words - len(words_reversed)))
        if len(words_reversed) != self.num_words:
            raise ParseError('Number too big')

        return words_reversed[::-1]


class MakeResultValue(NumericValue):
    def __init__(self, constituents: typ.List[NumericValue]):
        self.constituents = constituents
        self.num_words = sum(
            constituent.num_words for constituent in constituents
        )

    def as_word_array(self, asm: 'Assembler') -> typ.Optional[typ.List[int]]:
        word_array = []
        for constituent in self.constituents:
            constituent_result = constituent.as_word_array(asm)
            if constituent_result is None:
                return None
            word_array.extend(constituent_result)
        return word_array


class CodeValue(Value):
    def __init__(
        self, lines: typ.List[str], line_mapping: typ.List[int], origin: str
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
        assembler: 'Assembler', executing_context: 'Context'
    ) -> None:
        if len(self.arg_names) != len(args):
            raise ParseError(
                f"Expected {len(self.arg_names)} arg(s), got {len(args)}"
            )

        new_context = Context(self.context)
        for arg_name, arg_val in zip(self.arg_names, args):
            new_context.define_variable(arg_name, arg_val)

        parser = Parser(
            assembler, self.code_block.lines,
            self.code_block.line_mapping,
            self.code_block.origin
        )
        parser.parse_program(new_context)


class Context:
    def __init__(self, parent: typ.Optional['Context']):
        self.parent = parent
        self.instruction_macros: typ.Dict[str, InstructionMacro] = {}
        self.variables: typ.Dict[str, Value] = {}

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


class Assembler:
    def __init__(self) -> None:
        self.written_flags: typ.List[typ.Optional[bool]] = [None] * (2 ** 18)
        self.data_values: typ.List[typ.Tuple[int, NumericValue]] = []
        self.ip = 0

    def assemble_file(self, file_name: str) -> None:
        with open(file_name) as file:
            source = file.read()
        self.assemble_source(source, f'"{os.path.abspath(file_name)}"')

    def assemble_source(self, source: str, source_origin: str) -> None:
        sanitised = source.replace('\r', '')
        lines = sanitised.split('\n')

        line_mapping = [
            line_index + 1 for line_index in range(len(lines))
        ]
        parser = Parser(self, lines, line_mapping, source_origin)

        parser.parse_program(Context(None))

    def run_data_command(self, arguments: typ.List[Value]) -> None:
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

            self.data_values.append((start_ip, arg))

    def link_data(self) -> typ.List[typ.Optional[int]]:
        data: typ.List[typ.Optional[int]] = [None] * (2 ** 18)

        for value_start, numeric_value in self.data_values:
            word_array = numeric_value.as_word_array(self)

            # TODO: handle this and parse errors nicer
            assert word_array is not None

            for word_num, word in enumerate(word_array):
                assert data[word_num + value_start] is None
                data[word_num + value_start] = word

        return data

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

    def process_command(
        self, command_name: str,
        arguments: typ.List[Value],
        context: Context
    ) -> None:
        command_name = command_name.upper()

        if command_name == 'DATA':
            self.run_data_command(arguments)
        elif command_name == 'DEFINE':
            self.run_define_command(arguments, context)
        elif macro_command := context.find_instruction_macro(command_name):
            macro_command.execute(arguments, self, context)
        else:
            raise ParseError("Unknown command")


class Parser:
    IDENTIFIER_REGEX = r'[a-zA-Z_][a-zA-Z_0-9=]*'
    VARIABLE_USEAGE_REGEX = r'\$([a-zA-Z_][a-zA-Z_0-9=]*)'
    NUMERIC_REGEX = r'(0b[01]+)|(0x[a-fA-F0-9]+)|([1-9][0-9]*)|0'

    def __init__(
        self, assembler: Assembler, virtual_lines: typ.List[str],
        virtual_line_mapping: typ.List[int], original_file_name: str
    ) -> None:
        self.lines = [
            line + '\n' for line in virtual_lines
        ]
        self.line_num = 0
        self.column_num = 0
        self.assembler = assembler

        self.line_mapping = virtual_line_mapping
        self.source_origin = original_file_name

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
            args.append(self.parse_arg(context))

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

            return CodeValue(lines, line_mapping, self.source_origin)
        elif m := self.accept(self.VARIABLE_USEAGE_REGEX):
            variable_name = m.group(1)
            var_value = context.find_variable_value(variable_name)

            if var_value is not None:
                return var_value
            else:
                raise ParseError(f"Can't find variable {variable_name}")
        else:
            raise ParseError("Expected argument")

    def parse_command(self, ctx: Context) -> None:
        try:
            self.advance(0)
            command_name = self.expect(self.IDENTIFIER_REGEX).group(0)
            arguments = []

            while self.rest_of_line() != '\n':
                arguments.append(self.parse_arg(ctx))

                if self.rest_of_line() != '\n':
                    self.expect(',')

        except ParseError as parse_err:
            self.handle_parse_error(parse_err, False)
            raise

        self.assembler.process_command(command_name, arguments, ctx)

    def accept_comment(self) -> None:
        self.accept(r'[ \t]*[rR][eE][mM][^\n]*')

    def handle_parse_error(self, error: ParseError, full_line: bool) -> None:
        if self in error.registered_parsers:
            return

        offending_line_contents = self.lines[self.line_num][:-1]
        traceback = []
        traceback.append(
            f"At {self.source_origin} on line "
            f"{self.line_mapping[self.line_num]}:"
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

                self.parse_command(ctx)
                self.accept_comment()
                self.expect(r'\n')
        except ParseError as parse_err:
            self.handle_parse_error(parse_err, True)
            raise


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Need filename as argument")
        sys.exit(1)

    filename = sys.argv[1]

    assembler = Assembler()
    try:
        assembler.assemble_file(filename)
        data = assembler.link_data()
        print(" addr | data")
        for i, word in enumerate(data):
            if word is not None:
                print(f" {i:4} | {word:4}")
    except ParseError as err:
        err.print_info()
