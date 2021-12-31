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

    def __repr__(self) -> str:
        return f'IdentifierValue({repr(self.contents)})'


class NumericValue(Value):
    num_words: int

    @abc.abstractmethod
    def as_word_array(self, asm: 'Assembler') -> typ.List[int]:
        pass

    def as_integer(self, asm: 'Assembler') -> int:
        word_array = self.as_word_array(asm)

        return sum(
            word * 2 ** (6 * (self.num_words - i - 1))
            for i, word in enumerate(word_array)
        )

    def place_value(self, location: int, assembler: 'Assembler') -> None:
        pass


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
            raise ParseError(f'Number too big ({value}, {num_words})')

        return words_reversed[::-1]

    def __repr__(self) -> str:
        return f'ConstantNumericValue({self.value}_{self.num_words})'

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


class InlineLabelDeclarationValue(NumericValue):
    def __init__(self, name: str, initial: NumericValue):
        self.num_words = initial.num_words
        self.initial_value = initial
        self.name = name

    def as_word_array(self, asm: 'Assembler') -> typ.List[int]:
        return self.initial_value.as_word_array(asm)

    def place_value(self, location: int, assembler: 'Assembler') -> None:
        # TODO: The label will not be declared if this isn't called (e.g.
        #       because of some calculation based done off of it),
        #       which isn't the worse because then there'll just be a
        #       slightly vague error, but there should be a better message
        assembler.declare_label(self.name, location)


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

    def place_value(self, location: int, assembler: 'Assembler') -> None:
        offset = 0
        for consitituent in self.constituents:
            consitituent.place_value(location + offset, assembler)
            offset += consitituent.num_words


class ExtractedValue(NumericValue):
    num_words = 1

    def __init__(self, value: NumericValue, word_num: int):
        self.value = value
        self.word_num = word_num
        assert self.word_num < self.value.num_words

    def as_word_array(self, asm: 'Assembler') -> typ.List[int]:
        return [self.value.as_word_array(asm)[self.word_num]]


class CodeValue(Value):
    def __init__(
        self, lines: typ.List[str], line_mapping: typ.List[int], origin: str,
        context: 'Context'
    ):
        self.lines = lines
        self.line_mapping = line_mapping
        self.origin = origin
        self.context = context

        assert len(self.lines) == len(self.line_mapping)


class InstructionMacro:
    def __init__(
        self, name: str, code_block: CodeValue,
        arg_names: typ.List[str], is_internal: bool
    ) -> None:
        self.name = name
        self.code_block = code_block
        self.arg_names = arg_names
        self.context = code_block.context
        self.is_internal = is_internal

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
            self.code_block.origin, traceback, self.is_internal
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
            return self.parent.find_variable_value(name)
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
        self, previous: typ.Optional['ProgramTraceback'], lines: typ.List[str],
        program_line: str, line_origin: str, is_internal: bool,
        last_global_label: str
    ) -> None:
        self.previous = previous
        self.lines = lines

        self.program_line = program_line
        self.line_origin = line_origin
        self.is_internal = is_internal
        self.last_global_label = last_global_label

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

    def get_deepst_non_internal(self) -> 'ProgramTraceback':
        if self.is_internal:
            if self.previous is not None:
                return self.previous.get_deepst_non_internal()
            else:
                raise Exception('All internal!')
        else:
            return self


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
        self.assemble_source(source, os.path.abspath(file_name))

    def assemble_source(self, source: str, source_origin: str) -> None:
        sanitised = source.replace('\r', '')
        lines = sanitised.split('\n')

        line_mapping = [
            line_index + 1 for line_index in range(len(lines))
        ]
        parser = Parser(self, lines, line_mapping, source_origin, None, False)

        parser.parse_program(Context(None))

    def declare_label(
        self, label: str, location: typ.Optional[int] = None
    ) -> None:
        if label in self.label_values:
            raise ParseError(f'Redeclaration of label {label}!')
        self.label_values[label] = self.ip if location is None else location

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

            arg.place_value(start_ip, self)
            self.data_values.append((start_ip, arg, traceback))

    def link_data(self) -> 'compiled.CompiledProgram':
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

        if define_type in ('COMMAND', 'INTERNAL_COMMAND'):
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

            is_internal = {
                'INTERNAL_COMMAND': True,
                'COMMAND': False
            }[define_type]
            macro = InstructionMacro(
                macro_name, code_block, arg_names, is_internal
            )
            ctx.define_instruction(macro)
        elif define_type == 'VARIABLE':
            if len(args) != 3:
                raise ParseError('Need 3 args for variable definition')

            if not isinstance(args[1], IdentifierValue):
                raise ParseError("Need variable name")
            var_name = args[1].contents

            ctx.define_variable(var_name, args[2])
        else:
            raise ParseError(f'Unknown define type {define_type}')

    def run_set_command(self, args: typ.List[Value], ctx: Context) -> None:
        if len(args) < 1 or not isinstance(args[0], IdentifierValue):
            raise ParseError("Need sub-command for SET command")

        set_type = args[0].contents.upper()

        if set_type == 'VARIABLE':
            if len(args) != 3:
                raise ParseError('Need 3 args for variable val set')

            if not isinstance(args[1], IdentifierValue):
                raise ParseError("Need variable name")
            var_name = args[1].contents

            ctx.set_variable(var_name, args[2])
        else:
            raise ParseError(f'Unknown set command {set_type}')

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
        lookup_dirs.append(os.path.join(normalise(__file__), 'lib'))
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
        parser = Parser(self, lines, line_mapping, file_path, traceback)

        parser.parse_program(ctx)

    def run_loop_command(
        self, args: typ.List[Value], parent_ctx: Context,
        traceback: ProgramTraceback
    ) -> None:
        if len(args) != 3:
            raise ParseError('Need three args for loop')

        condition_name_arg = args[0]
        if not isinstance(condition_name_arg, IdentifierValue):
            raise ParseError('Need loop condition variable')
        condition_var_name = condition_name_arg.contents

        condition_code = args[1]
        if not isinstance(condition_code, CodeValue):
            raise ParseError('Need condition code')

        body_code = args[2]
        if not isinstance(body_code, CodeValue):
            raise ParseError('Need loop body')

        context = Context(parent_ctx)

        context.define_variable(
            condition_var_name, IdentifierValue('NOT_SET')
        )
        while True:
            context.set_variable(
                condition_var_name, IdentifierValue('NOT_SET')
            )
            condition_parser = Parser(
                self, condition_code.lines, condition_code.line_mapping,
                condition_code.origin, traceback
            )
            condition_parser.parse_program(context)

            condition_value = context.find_variable_value(condition_var_name)
            if condition_value is None:
                raise ParseError("Condition variable not defined")

            should_break: bool
            if isinstance(condition_value, IdentifierValue):
                contents = condition_value.contents.upper()
                if contents == 'FALSE':
                    should_break = True
                elif contents == 'TRUE':
                    should_break = False
                else:
                    raise ParseError(f'Unknown flag {contents}')
            elif isinstance(condition_value, NumericValue):
                try:
                    should_break = all(
                        word == 0
                        for word in condition_value.as_word_array(self)
                    )
                except ValueNotReadyException:
                    raise ParseError('Condition value not ready')
            else:
                raise ParseError(f"Condition can't be {type(condition_value)}")

            if should_break:
                break

            body_parser = Parser(
                self, body_code.lines, body_code.line_mapping,
                body_code.origin, traceback
            )
            body_parser.parse_program(context)

    def run_if_command(
        self, args: typ.List[Value], parent_ctx: Context,
        traceback: ProgramTraceback
    ) -> None:
        if len(args) != 2:
            # TODO: else
            raise ParseError('Need two args for IF')

        condition_value = args[0]
        if not isinstance(condition_value, NumericValue):
            raise ParseError('Condition must be numeric')

        try:
            condition = condition_value.as_integer(self) != 0
        except ValueNotReadyException:
            raise ParseError('IF condition not ready')

        if not condition:
            return

        body = args[1]
        if not isinstance(body, CodeValue):
            raise ParseError('Need code block for IF')

        context = Context(body.context)

        body_parser = Parser(
            self, body.lines, body.line_mapping,
            body.origin, traceback
        )
        body_parser.parse_program(context)

    def run_up_command(
        self, args: typ.List[Value], command_ctx: Context,
        traceback: ProgramTraceback
    ) -> None:
        if len(args) != 1:
            # TODO: else
            raise ParseError('Need one args for UP')

        body = args[0]
        if not isinstance(body, CodeValue):
            raise ParseError('Need code block for UP')

        context = body.context.parent
        if context is None:
            raise ParseError('UP in top level context')

        body_parser = Parser(
            self, body.lines, body.line_mapping,
            body.origin, traceback
        )
        body_parser.parse_program(context)

    def run_assert_command(self, args: typ.List[Value]) -> None:
        if len(args) != 1:
            raise ParseError('Expected 1 arg to ASSERT')

        if not isinstance(args[0], NumericValue):
            raise ParseError('Expected numeric argument to ASSERT')

        try:
            condition = args[0].as_integer(self)
        except ValueNotReadyException:
            raise ParseError('Value to ASSERT not ready')

        if condition == 0:
            raise ParseError('Assertion failure')

    def run_skip_command(self, args: typ.List[Value]) -> None:
        if len(args) != 1:
            raise ParseError('Expected 1 arg to SKIP_DATA')

        if not isinstance(args[0], NumericValue):
            raise ParseError('Expected numeric argument to SKIP_DATA')

        try:
            as_int = args[0].as_integer(self)
        except ValueNotReadyException:
            raise ParseError('Value to SKIP_DATA not ready')

        self.ip += as_int
        assert self.ip < 2 ** 18

    def process_command(
        self, command_name: str,
        arguments: typ.List[Value],
        context: Context, traceback: ProgramTraceback
    ) -> None:
        command_name = command_name.upper()

        if command_name == 'DATA':
            self.run_data_command(arguments, traceback)
        elif command_name == 'SKIP_DATA':
            self.run_skip_command(arguments)
        elif command_name == 'DEFINE':
            self.run_define_command(arguments, context)
        elif command_name == 'SET':
            self.run_set_command(arguments, context)
        elif command_name == 'ASSERT':
            self.run_assert_command(arguments)
        elif command_name == 'INCLUDE':
            self.run_include_command(arguments, context, traceback)
        elif command_name == 'LOOP':
            self.run_loop_command(arguments, context, traceback)
        elif command_name == 'IF':
            self.run_if_command(arguments, context, traceback)
        elif command_name == 'UP':
            self.run_up_command(arguments, context, traceback)
        elif command_name == 'DEBUG_OUT':
            print('DEBUG OUT', arguments)
        elif macro_command := context.find_instruction_macro(command_name):
            macro_command.execute(arguments, self, context, traceback)
        else:
            raise ParseError(f'Unknown command {command_name}')


class Parser:
    IDENTIFIER_REGEX = r'[a-zA-Z_][a-zA-Z_0-9]*'
    VARIABLE_USEAGE_REGEX = r'\$([a-zA-Z_][a-zA-Z_0-9]*)'
    NUMERIC_REGEX = r'(0b[01]+)|(0x[a-fA-F0-9]+)|([1-9][0-9]*)|0'
    MAIN_LABEL_REGEX = r'(\.|:)([a-zA-Z_][a-zA-Z_0-9.]*)'
    DECLARE_INLINE_LABEL_REGEX = r'%(\.|:)([a-zA-Z_][a-zA-Z_0-9.]*)'

    def __init__(
        self, assembler: Assembler, virtual_lines: typ.List[str],
        virtual_line_mapping: typ.List[int], original_file_name: str,
        parent_traceback: typ.Optional[ProgramTraceback],
        is_internal: typ.Optional[bool] = None
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

        if is_internal is not None:
            self.is_internal = is_internal
        else:
            assert self.parent_traceback is not None
            self.is_internal = self.parent_traceback.is_internal

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

    def get_numeric_values_from_args(
        self, num: int, args: typ.List[Value]
    ) -> typ.Tuple[int, typ.List[int]]:
        if len(args) != num:
            raise ParseError(f'Expected {num} arguments, got {len(args)}')

        ints = []
        largest_word_size = 0
        for arg in args:
            if not isinstance(arg, NumericValue):
                if arg.backtrace:
                    arg.backtrace.trigger_error('Expected numeric value')
                else:
                    raise ParseError('Expected numeric value')

            try:
                largest_word_size = max(
                    largest_word_size, arg.num_words
                )
                integer_value = arg.as_integer(self.assembler)
            except ValueNotReadyException:
                if arg.backtrace:
                    arg.backtrace.trigger_error('Value not ready')
                else:
                    raise ParseError('Value not ready')

            ints.append(integer_value)

        return largest_word_size, ints

    def parse_function_call(self, name: str, context: Context) -> Value:
        args = []
        while True:
            arg = self.parse_arg(context)
            arg.backtrace = self.current_traceback(context)
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
        elif name == 'is_lt':
            num_words, values = self.get_numeric_values_from_args(2, args)
            a, b = values

            return ConstantNumericValue(1 if a < b else 0, 1)
        elif name == 'is_pow_of_two':
            num_words, values = self.get_numeric_values_from_args(1, args)
            a, = values
            is_pow_of_2 = a > 1 and a & (a - 1) == 0

            return ConstantNumericValue(1 if is_pow_of_2 else 0, 1)
        elif name == 'is_eq':
            if len(args) != 2:
                raise ParseError('Expected two args')

            if isinstance(args[0], NumericValue):
                num_words, values = self.get_numeric_values_from_args(2, args)
                a, b = values
                # ignore num_words
                return ConstantNumericValue(1 if a == b else 0, 1)
            elif isinstance(args[0], IdentifierValue):
                if not isinstance(args[1], IdentifierValue):
                    raise ParseError('Second arg not idenfitier in is_eq')

                return ConstantNumericValue(
                    1 if args[0].contents == args[1].contents else 0, 1
                )
            else:
                raise ParseError(f"Canm't check is_eq for {type(args[0])}")
        elif name == 'not':
            num_words, values = self.get_numeric_values_from_args(1, args)
            a, = values

            return ConstantNumericValue(1 if a == 0 else 0, 1)
        elif name == 'plus':
            num_words, values = self.get_numeric_values_from_args(2, args)
            a, b = values
            # overflow will be catched in word array conversion
            return ConstantNumericValue(a + b, num_words)
        elif name == 'minus':
            num_words, values = self.get_numeric_values_from_args(2, args)
            a, b = values

            if b > a:
                raise ParseError('Minus giving negative value')

            return ConstantNumericValue(a - b, num_words)
        elif name == 'zero_extend_numeric':
            num_words, values = self.get_numeric_values_from_args(2, args)
            a, b = values

            return ConstantNumericValue(a, b)
        elif name == 'concat_ident':
            if len(args) < 2:
                raise ParseError('Need at least two identifiers to concat')

            segments = []
            for arg in args:
                if not isinstance(arg, IdentifierValue):
                    raise ParseError(
                        f'Need identifier to concat, not {type(arg)}'
                    )
                segments.append(arg.contents)

            return IdentifierValue(''.join(segments))
        elif name == 'read_var':
            if len(args) != 1 or not isinstance(args[0], IdentifierValue):
                raise ParseError('Expected ident for read_var')

            var_value = context.find_variable_value(args[0].contents)
            if var_value is None:
                raise ParseError(f"Can't find var {args[0].contents}")

            return var_value
        elif name == 'hi':
            if len(args) != 1:
                raise ParseError('Need 1 arg for hi')
            if not isinstance(args[0], NumericValue):
                raise ParseError('Expected numeric value for hi command')

            num_words = args[0].num_words
            if num_words <= 1:
                raise ParseError('need more than 1 word for hi()')
            desired_word_num = 0

            return ExtractedValue(args[0], desired_word_num)
        elif name == 'mod':
            num_words, values = self.get_numeric_values_from_args(2, args)
            a, b = values
            if b == 0:
                raise ParseError('mod by 0')

            return ConstantNumericValue(a % b, num_words)
        else:
            raise ParseError(f"Unknown method {name}")

    def current_traceback(self, context: Context) -> ProgramTraceback:
        offending_line_contents = self.lines[self.last_command_line_num][:-1]

        line_number = self.line_mapping[self.last_command_line_num]

        full_line_origin = (
            f'At "{self.source_origin}" on line '
            f'{line_number}:'
        )
        line_origin = f'{os.path.basename(self.source_origin)}:{line_number}'

        program_line = f"    {offending_line_contents}"
        is_internal = self.is_internal

        traceback = [full_line_origin, program_line]

        return ProgramTraceback(
            self.parent_traceback, traceback, program_line, line_origin,
            is_internal, context.last_global_label
        )

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

        elif m := self.accept(self.MAIN_LABEL_REGEX):
            is_local = m.group(1) == '.'
            name = m.group(2)

            if is_local:
                if context.last_global_label == '':
                    raise ParseError('Local without previous global label')
                label = f'{context.last_global_label}.{name}'
            else:
                label = name

            return LabelValue(label)

        elif m := self.accept(self.DECLARE_INLINE_LABEL_REGEX):
            is_local = m.group(1) == '.'
            name = m.group(2)

            if is_local:
                if context.last_global_label == '':
                    raise ParseError('Local without previous global label')
                label = f'{context.last_global_label}.{name}'
            else:
                context.last_global_label = name.split('.', 2)[0]
                label = name

            if not is_local:
                # seems weird to declare a global inline label
                raise ParseError("No global inline labels")

            initial_value: NumericValue = ConstantNumericValue(0, 1)

            if self.accept(r'='):
                parsed_value = self.parse_arg(context)
                if not isinstance(parsed_value, NumericValue):
                    raise ParseError("Expected numeric value for initial val")
                initial_value = parsed_value

            return InlineLabelDeclarationValue(label, initial_value)

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
                lines, line_mapping, self.source_origin, context
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
                command_name, arguments,
                ctx, self.current_traceback(ctx)
            )
        except ParseError as parse_err:
            self.handle_parse_error(parse_err, True)
            raise

    def accept_label_declaration(self, ctx: Context) -> bool:
        match = self.accept(self.MAIN_LABEL_REGEX)

        if not match:
            return False

        is_local = match.group(1) == '.'
        name = match.group(2)

        if is_local:
            if ctx.last_global_label == '':
                raise ParseError('Local without previous global label')
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
            f'At "{self.source_origin}" on line '
            f'{self.line_mapping[line_num]}:'
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
                lines: typ.List[str] = []
                word.traceback.gather_lines(lines)
                print(f" {i:4} | {word.value:4} | {lines[-9]} | {lines[-8]}")
    except AssemblyError as err:
        err.print_info()


if __name__ == '__main__':
    main()
