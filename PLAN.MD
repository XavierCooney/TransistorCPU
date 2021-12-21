## Explicit registers
Total: 53 bits => 424 transistors

 - PC (3 words minus 2 bits, total 16 bits)
 - A (1 word, 6 bits)
 - Opcode (1 word, 6 bits)
 - MAR (3 words, 18 bits)
 - Data input register (1 word + 1 bit for ready flag, total 7 bits)

## Execution Steps:
 1. Fetch
    1. Read from RAM with PC selected at offset 0 into Opcode
 2. Execute based on Opcode
    1. Read memeory into A:
        1. Read from RAM with PC selected at offset 1 into MAR0
        2. Read from RAM with PC selected at offset 2 into MAR1
        3. Read from RAM with PC selected at offset 3 into MAR2
        4. Read from RAM with MAR into A
    2. Write memeory from A:
        1. Read from RAM with PC selected at offset 1 into MAR0
        2. Read from RAM with PC selected at offset 2 into MAR1
        3. Read from RAM with PC selected at offset 3 into MAR2
        4. Write to RAM with MAR from A
    3. Increment A
        1. Write ALU output of inc(A) into MAR0 (or any other temp)
        2. Write MAR0 into A
    4. NAND A with immediate operand (maybe)
        1. Read from RAM with PC selected at offset 1 into MAR0
        2. Write ALU output of NAND(MAR0, A) into MAR1
        3. Write MAR1 into A
    5. Unconditional jump
        1. Read from RAM with PC selected at offset 1 into MAR0
        2. Read from RAM with PC selected at offset 2 into MAR1
        3. Read from RAM with PC selected at offset 3 into MAR2
        4. Write MAR to PC
    6. Conditional jump (A=0, input ready)
        1. Read from RAM with PC selected at offset 1 into MAR0
        2. Read from RAM with PC selected at offset 2 into MAR1
        3. Read from RAM with PC selected at offset 3 into MAR2
        4. Write MAR to PC
    7. Read memeory into A based off A:
        1. Read from RAM with PC selected at offset 1 into MAR0
        2. Read from RAM with PC selected at offset 2 into MAR1
        3. Write A to MAR2
        4. Read from RAM with MAR into A
    8. Output A
        1. Read from RAM with PC selected at offset 1 into MAR2
        2. Perform write of A to output, based on MAR2?
 3. Increment
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
 1. Incrementor: Maybe 8 bits wide? So blocks of 256 instructions. So then 72 transistors
