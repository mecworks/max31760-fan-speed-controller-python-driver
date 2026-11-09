"""Probe v4: use readfrom_mem (universal MicroPython I2C API)."""
import sys, time, serial

PORT = "COM16"
BAUD = 115200

# Flat lines, no multi-line blocks, no single-line if (REPL eats those into continuation)
CODE_LINES = [
    "import machine",
    "i2c=machine.I2C(0,scl=machine.Pin(1),sda=machine.Pin(0))",
    "found=i2c.scan()",
    'print("SCAN:",[hex(a) for a in found])',
    # Read local temp (regs 0x58-0x59)
    "lt=i2c.readfrom_mem(0x50,0x58,2)",
    # Read remote temp (regs 0x56-0x57)
    "rt=i2c.readfrom_mem(0x50,0x56,2)",
    # Decode without if: use arithmetic sign-extension trick
    # raw16 sign-extend: ((raw ^ 0x8000) - 0x8000) gives signed value
    'lr=(((lt[0]<<8)|lt[1])^0x8000)-0x8000',
    'rr=(((rt[0]<<8)|rt[1])^0x8000)-0x8000',
    'print("LOCAL=%.3fC raw=%02X%02X"%((lr>>5)/8.0,lt[0],lt[1]))',
    'print("REMOTE=%.3fC raw=%02X%02X"%((rr>>5)/8.0,rt[0],rt[1]))',
    # Status register
    "sr=i2c.readfrom_mem(0x50,0x5A,1)",
    'print("STATUS=0x%02X"%sr[0])',
    # Control registers
    "cr=i2c.readfrom_mem(0x50,0x00,4)",
    'print("CR1=0x%02X CR2=0x%02X CR3=0x%02X FFDC=0x%02X"%(cr[0],cr[1],cr[2],cr[3]))',
]

def main():
    ser = serial.Serial(PORT, BAUD, timeout=2)
    time.sleep(1)
    ser.reset_input_buffer()
    
    # Wake the REPL
    ser.write(b"\r\n")
    time.sleep(0.5)
    ser.reset_input_buffer()
    
    # Clean prompt
    ser.write(b"\x04")
    time.sleep(0.5)
    ser.reset_input_buffer()
    
    # Send each line
    for line in CODE_LINES:
        ser.write((line + "\r").encode())
        time.sleep(0.12)
    
    # Wait for execution + prints
    time.sleep(2)
    
    # Collect output
    output = ""
    while ser.in_waiting > 0:
        output += ser.read_all().decode(errors="replace")
    
    print("=== RAW ===")
    print(output)
    print("===========")
    
    # Extract results
    for line in output.splitlines():
        s = line.strip()
        if any(k in s for k in ("SCAN:", "LOCAL=", "REMOTE=", "STATUS=", "CR1=", "ERR", "Error")):
            print(s)
    
    ser.close()

if __name__ == "__main__":
    main()
