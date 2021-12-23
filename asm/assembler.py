import re
import typing as typ


class ParseError(Exception):
    pass


class Argument:
    pass


class IdentifierArgument(Argument):
    def __init__(self, contents: str):
        self.contents = contents


class NumericArgument(Argument):
    def __init__(self, value: int, num_words: int):
        self.value = value
        self.num_words = num_words

    def as_word_array(self) -> typ.List[int]:
        words_reversed = []
        val = self.value
        while val:
            words_reversed.append(val % 64)
            val //= 64

        words_reversed.extend([0] * (self.num_words - len(words_reversed)))
        if len(words_reversed) != self.num_words:
            raise ParseError('Number too big')

        return words_reversed[::-1]


class CodeArgument(Argument):
    def __init__(self, lines: str):
        self.lines = lines


class InstructionMacro:
    def __init__(
        self, name: str, code_block: CodeArgument,
        arg_names: typ.List[str], context: 'Context'
    ) -> None:
        self.name = name
        self.code_block = code_block
        self.arg_names = arg_names
        self.context = context

    def execute(
        self, args: typ.List['Argument'],
        assembler: 'Assembler', context: 'Context'
    ) -> None:
        if len(self.arg_names) != len(args):
            raise ParseError(
                f"Expected {len(self.arg_names)} args, got {len(args)}"
            )

        new_context = Context(self.context)
        for arg_name, arg_val in zip(self.arg_names, args):
            new_context.define_variable(arg_name, arg_val)

        parser = Parser(assembler, self.code_block.lines)
        parser.parse_program(self.context)


class Context:
    def __init__(self, parent: typ.Optional['Context']):
        self.parent = parent
        self.instruction_macros: typ.Dict[str, InstructionMacro] = {}
        self.variables: typ.Dict[str, Argument] = {}

    def find_instruction_macro(
        self, name: str
    ) -> typ.Optional[InstructionMacro]:
        if name in self.instruction_macros:
            return self.instruction_macros[name]
        if self.parent is not None:
            return self.parent.find_instruction_macro(name)
        return None

    def find_variable_value(self, name: str) -> typ.Optional[Argument]:
        if name in self.variables:
            return self.variables[name]
        if self.parent is not None:
            return self.find_variable_value(name)
        return None

    def define_variable(self, var_name: str, var_value: Argument) -> None:
        assert var_name not in self.variables
        self.variables[var_name] = var_value


class Assembler:
    def __init__(self) -> None:
        self.data: typ.List[typ.Optional[int]] = [None] * (2 ** 18)
        self.ip = 0

    def assemble_file(self, file_name: str) -> None:
        with open(file_name) as file:
            source = file.read()
        self.assemble_source(source)

    def assemble_source(self, source: str) -> None:
        parser = Parser(self, source)
        parser.parse_program(Context(None))

    def run_data_command(self, arguments: typ.List[Argument]) -> None:
        for arg in arguments:
            if isinstance(arg, NumericArgument):
                words = arg.as_word_array()
                for word in words:
                    if self.data[self.ip] is not None:
                        if self.data[self.ip] != word:
                            raise ParseError('Invalid rewrite of data')
                    else:
                        self.data[self.ip] = word
                        self.ip += 1
                        assert self.ip < 2**16
            else:
                assert False, f"DATA expects numeric arg, not {type(arg)}"

    def process_command(
        self, command_name: str,
        arguments: typ.List[Argument],
        context: Context
    ) -> None:
        command_name = command_name.upper()

        if command_name == 'DATA':
            self.run_data_command(arguments)
        elif macro_command := context.find_instruction_macro(command_name):
            macro_command.execute(arguments, self, context)
        else:
            assert False, "Unknown command "


class Parser:
    IDENTIFIER_REGEX = r'[a-zA-Z_][a-zA-Z_0-9=]*'
    NUMERIC_REGEX = r'(0b[01]+)|(0x[a-fA-F0-9]+)|([1-9][0-9]*)|0'

    def __init__(self, assembler: Assembler, source_contents: str) -> None:
        source_contents = source_contents.replace('\r', '')
        self.lines = [
            line + '\n' for line in source_contents.split('\n')
        ]
        self.line_num = 0
        self.column_num = 0
        self.assembler = assembler

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

    def parse_arg(self, context: Context) -> Argument:
        if m := self.accept(self.IDENTIFIER_REGEX):
            return IdentifierArgument(m.group(0))
        elif m := self.accept(self.NUMERIC_REGEX, False):
            value = int(m.group(0), base=0)
            word_size = 1
            if m_word_size := self.accept(r'_([1-3])'):
                word_size = int(m_word_size.group(1))
            self.expect("")
            return NumericArgument(value, word_size)
        else:
            raise ParseError("Expected argument")

    def parse_command(self, ctx: Context) -> None:
        self.advance(0)
        command_name = self.expect(self.IDENTIFIER_REGEX).group(0)
        arguments = []

        while self.rest_of_line() != '\n':
            arguments.append(self.parse_arg(ctx))
            if self.rest_of_line() != '\n':
                self.expect(',')

        self.assembler.process_command(command_name, arguments, ctx)

    def accept_comment(self) -> None:
        self.accept(r'[ \t]*[rR][eE][mM][^\n]*')

    def parse_program(self, ctx: Context) -> None:
        try:
            while self.line_num < len(self.lines):
                self.accept_comment()
                if self.accept(r'\n'):
                    continue

                self.parse_command(ctx)
                self.accept_comment()
                self.expect(r'\n')
        except ParseError:
            print(f"Around line {self.line_num}:")
            print(f"    {self.lines[self.line_num][:-1]}")
            print("    " + " " * self.column_num + "^")
            raise
