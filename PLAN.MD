## Explicit registers
Total: 53 bits => 424 transistors

 - PC (3 words minus 2 bits, total 16 bits)
 - A (1 word, 6 bits)
 - Opcode (1 word, 6 bits)
 - MAR (3 words, 18 bits)
 - Data input register (1 word + 1 bit for ready flag, total 7 bits)
memor
## Execution Steps:
 1. Fetch
    1. Read from RAM with PC selected at offset 0 into Opcode
 2. Execute based on Opcode
    1. Read memory into A (100000):
        1. Read from RAM with PC selected at offset 1 into MAR2
        2. Read from RAM with PC selected at offset 2 into MAR1
        3. Read from RAM with PC selected at offset 3 into MAR0
        4. Read from RAM with MAR into A
    2. Write memory from A (110000):
        1. Read from RAM with PC selected at offset 1 into MAR2
        2. Read from RAM with PC selected at offset 2 into MAR1
        3. Read from RAM with PC selected at offset 3 into MAR0
        4. Write to RAM with MAR from A
    3. Read memeory into A based off A (101000):
        1. Read from RAM with PC selected at offset 1 into MAR2
        2. Read from RAM with PC selected at offset 2 into MAR1
        3. Write A to MAR0
        4. Read from RAM with MAR into A
    4. Increment A (010000):
        1. Write ALU output of inc(A) into MAR0 (or any other temp)
        2. Write MAR0 into A
    5. NAND A with immediate operand (maybe)
        1. Read from RAM with PC selected at offset 1 into MAR0
        2. Write ALU output of NAND(MAR0, A) into MAR1
        3. Write MAR1 into A
    6. Unconditional jump (001100)
        1. Read from RAM with PC selected at offset 1 into MAR2
        2. Read from RAM with PC selected at offset 2 into MAR1
        3. Read from RAM with PC selected at offset 3 into MAR0
        4. Write MAR to PC
    7. Conditional jump [A = 0: 001010, input ready: 001001]
        1. Read from RAM with PC selected at offset 1 into MAR0
        2. Read from RAM with PC selected at offset 2 into MAR1
        3. Read from RAM with PC selected at offset 3 into MAR2
        4. Write MAR to PC
    8. Output A (000010)
        1. Read from RAM with PC selected at offset 1 into MAR2
        2. Perform write of A to output, based on MAR2?
 3. Increment PC
    1. Write inc(PC) to MAR
    2. Write MAR to PC

## Flags
Total: 17

 - Write to bus
 - Read from bus
 - RAM address is PC
 - RAM address is MAR
 - RAM offset (2 bits)
 - Read bus into MAR0
 - Read bus into MAR1
 - Read bus into MAR2
 - Read bus into A
 - Write A to bus
 - Write inc(A) to bus
 - Write MAR0 to bus
 - Maybe NAND stuff???
 - Write MAR to PC
 - ALU inc source flag (A vs PC)
 - Input ready flag
 - Perform output


## Other big cirucits
 1. Incrementor: Maybe 10 bits wide? So blocks of 1024 instructions. So then 91 transistors
