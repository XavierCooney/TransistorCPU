import typing as typ

VOLTAGE = 5
BITS = 6


def bits_suffix(prefix: str) -> typ.List[str]:
    return [f'{prefix}{i}' for i in range(BITS)]
