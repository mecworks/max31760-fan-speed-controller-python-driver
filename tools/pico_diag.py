"""Diagnostic: enumerate the I2C object's actual API on this MicroPython build."""
import serial
import time

PORT = "COM16"
BAUD = 115200


def main():
    ser = serial.Serial(PORT, BAUD, timeout=1)
    time.sleep(0.5)
    ser.reset_input_buffer()
    ser.write(b"\x02")
    time.sleep(0.6)
    ser.reset_input_buffer()

    def run(code, timeout=8.0):
        ser.reset_input_buffer()
        ser.write(b"\x03")
        time.sleep(0.2)
        ser.reset_input_buffer()
        ser.write((code + "\r\n").encode())
        start = time.time()
        out = b""
        while time.time() - start < timeout:
            d = ser.read(512)
            if d:
                out += d
                if out.endswith(b">>> ") or b">>> \n" in out[-12:]:
                    time.sleep(0.15)
                    out += ser.read(512)
                    break
        return out.decode(errors="replace")

    cmds = [
        ("dir(i2c)",
         "import machine; i2c=machine.I2C(0,sda=machine.Pin(0),scl=machine.Pin(1)); print(sorted(dir(i2c)))"),
        ("method presence",
         "print('scan',hasattr(i2c,'scan'),'writeto',hasattr(i2c,'writeto'),'readfrom',hasattr(i2c,'readfrom'),'readinto',hasattr(i2c,'readinto'),'write',hasattr(i2c,'write'),'transaction',hasattr(i2c,'transaction'),'mem_read',hasattr(i2c,'mem_read'))"),
        ("try readfrom(addr,nbytes)",
         "b=i2c.readfrom(0x50,2); print('rf_addr_n',list(b))"),
        ("try readinto after writeto pointer",
         "i2c.writeto(0x50,bytes([0x58])); b=bytearray(2); i2c.readinto(b); print('ri_after_wt',[hex(x) for x in b])"),
    ]
    for label, code in cmds:
        print(f"--- {label} ---")
        print(run(code).strip())
        print()

    ser.close()


if __name__ == "__main__":
    main()
