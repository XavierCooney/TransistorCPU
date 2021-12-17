# A samll module to solve sytems of linear equations for custom sim
import math
import typing as typ
from collections import defaultdict


class System:
    def __init__(self) -> None:
        self.vars: typ.Dict[str, int] = {}
        self.rows: typ.Dict[str, int] = {}

        MatEntryType = typ.Dict[typ.Tuple[int, int], float]
        # self.mat_entries indexed by (row, col)
        self.mat_entries: MatEntryType = defaultdict(int)
        self.const_vec: typ.Dict[int, float] = defaultdict(int)

    def var_index(self, var: str) -> int:
        if var not in self.vars:
            self.vars[var] = len(self.vars)

        return self.vars[var]

    def row_index(self, row_name: str) -> int:
        if row_name not in self.rows:
            self.rows[row_name] = len(self.rows)

        return self.rows[row_name]

    def add_term(
        self, coeff: float, term_var_name: str, row_var_name: str
    ) -> None:
        term_var = self.var_index(term_var_name)
        row_var = self.row_index(row_var_name)

        self.mat_entries[(row_var, term_var)] += coeff

    def add_constant(self, constant: float, row_var_name: str) -> None:
        row_var = self.row_index(row_var_name)
        self.const_vec[row_var] += constant

    def solve(self) -> typ.Dict[str, float]:
        # Delay import so no issue if sim not invoked
        import numpy
        import scipy.sparse  # type: ignore
        import scipy.sparse.linalg  # type: ignore

        num_rows = len(self.rows)
        num_vars = len(self.vars)
        assert num_rows == num_vars

        # TODO: construct the sparse matrix better?
        matrix = scipy.sparse.lil_matrix((num_rows, num_vars))
        for coord, coefficient in self.mat_entries.items():
            matrix[coord] = coefficient

        b_vec = numpy.zeros((num_rows,))
        for index, constant in self.const_vec.items():
            b_vec[index] = constant

        solution = scipy.sparse.linalg.spsolve(matrix.tocsr(), b_vec)

        return {
            var_name: solution[var_index]
            for var_name, var_index in self.vars.items()
        }


if __name__ == '__main__':
    # x = 5, y = -7
    # 2x + 3y = -11     (1)
    # x - y = 12        (2)
    # x + y = -2        (3)

    system = System()

    system.add_term(2, 'x', '1')
    system.add_term(3, 'y', '1')
    system.add_constant(-11, '1')

    system.add_term(-1, 'y', '2')
    system.add_term(1, 'x', '2')
    system.add_constant(12, '2')

    result = system.solve()

    print(result)

    assert len(result) == 2
    assert math.isclose(result['x'], 5)
    assert math.isclose(result['y'], -7)
