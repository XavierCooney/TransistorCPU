import typing as typ
from . import assembler

tests: typ.List[typ.Tuple[str, str, typ.List[typ.Optional[int]]]] = []


def add_simple_test(
    name: str, src: str,
    data: typ.List[typ.Optional[int]],
    offset: int = 0
) -> None:
    expected: typ.List[typ.Optional[int]] = [None] * (2 ** 18)

    for i, word in enumerate(data):
        if isinstance(word, int):
            assert 0 <= word < 64
        expected[offset + i] = word
    tests.append((name, src, expected))


add_simple_test("test1", """DATA""", [])
add_simple_test("test2", """DATA 0""", [0])
add_simple_test("test3", """DATA 0, 1""", [0, 1])
add_simple_test("test4", """DATA 4, 3,""", [4, 3])
add_simple_test("test5", """DATA 4, 3""", [4, 3, None])
add_simple_test("test6", """
DATA 4, 3
DATA 5, 6
""", [4, 3, 5, 6])

add_simple_test("macro1", """
DEFINE COMMAND, DO_SOMETHING, a, b, {
    DEFINE VARIABLE, c, 3
    DATA $a, $c, $b
}
DO_SOMETHING 8, 9
""", [8, 3, 9])

add_simple_test("macro2", """
DEFINE COMMAND, DO_SOMETHING, a, b, {
    DEFINE COMMAND, WOW, f, e, g, {
        DATA $e, $f, $g
    }
    DEFINE VARIABLE, c, 3
    WOW $a, $c, $b
}
DO_SOMETHING 8, 9
""".strip(), [3, 8, 9])

add_simple_test("include", """
INCLUDE common

INC_A
""".strip(), [16, 0, 0, 0])


if __name__ == '__main__':
    for test in tests:
        # assembler.
        test_name, test_source, test_expected = test
        print(f" == {test_name} ==")
        asm = assembler.Assembler()

        try:
            asm.assemble_source(test[1], f'<test {test_name}>')
            compiled_program = asm.link_data()
            data = [
                word.value if word is not None else None
                for word in compiled_program.data
            ]
        except assembler.AssemblyError as err:
            err.print_info()
            break

        if data != test_expected:
            first_discrepency = [
                actual != expected
                for actual, expected in zip(data, test_expected)
            ].index(True)

            print(f"Discrepancy at {first_discrepency}:")
            explanation_start = max(0, first_discrepency - 5)

            for row_num, row in enumerate((test_expected, data)):
                print(["Expected", "Actual  "][row_num], end='  ')
                for term in row[explanation_start:explanation_start+10]:
                    if term is None:
                        printed_term = '__'
                    else:
                        printed_term = str(term)
                    print(f' {printed_term:>4}', end='')
                print()
            skip_terms = first_discrepency - explanation_start
            prefix = " " * (5 * skip_terms + 10)
            print(prefix + " ^^^^")
            print(prefix + f"@{first_discrepency}".rjust(5))
