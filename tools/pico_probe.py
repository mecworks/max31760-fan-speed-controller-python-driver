"""Final MAX31760 verification on RPi Pico W first edition (COM16).

This MicroPython build exposes register access as readfrom_mem/writeto_mem
(non-standard names; no mem_read/mem_write/begin_transaction). Confirms
bidirectional comms and decodes live sensor values.
"""
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
        ("Version",
         "import sys; print('MP',sys.version); print('PLATFORM',sys.platform)"),
        ("Init I2C0 + scan",
         "import machine; i2c=machine.I2C(0,sda=machine.Pin(0),scl=machine.Pin(1)); print('scan',i2c.scan())"),
        ("LOCAL_TEMP via readfrom_mem(0x50,0x58,2)",
         "raw=int.from_bytes(i2c.readfrom_mem(0x50,0x58,2),'big'); v=raw-65536 if raw>=32768 else raw; print('local_C',round(v/64.0,3))"),
        ("REMOTE_TEMP via readfrom_mem(0x50,0x56,2)",
         "raw=int.from_bytes(i2c.readfrom_mem(0x50,0x56,2),'big'); v=raw-65536 if raw>=32768 else raw; print('remote_C',round(v/64.0,3))"),
        ("STATUS/CR1/PWM_VALUE",
         "sr=i2c.readfrom_mem(0x50,0x5A,1)[0]; cr1=i2c.readfrom_mem(0x50,0x00,1)[0]; pw=i2c.readfrom_mem(0x50,0x51,1)[0]; print('SR',hex(sr),'CR1',hex(cr1),'PWMV',pw)"),
        ("TACH TC1/TC2",
         "tc1=int.from_bytes(i2c.readfrom_mem(0x50,0x52,2),'big'); tc2=int.from_bytes(i2c.readfrom_mem(0x50,0x54,2),'big'); print('TC1',tc1,'TC2',tc2)"),
        ("Write-path RMW no-op CR1 via writeto_mem",
         "cr1=i2c.readfrom_mem(0x50,0x00,1)[0]; i2c.writeto_mem(0x50,0x00,bytes([cr1])); print('rw_ok',i2c.readfrom_mem(0x50,0x00,1)[0]==cr1)"),
    ]
    for label, code in cmds:
        print(f"--- {label} ---")
        print(run(code).strip())
        print()

    ser.close()


if __name__ == "__main__":
    main()
