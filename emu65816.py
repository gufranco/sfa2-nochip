STEP_LIMIT = 2_000_000


class StepLimit(Exception):
    pass


class Unsupported(Exception):
    pass


class Cpu:
    def __init__(self, memory, step_limit=STEP_LIMIT):
        self.memory = memory
        self.step_limit = step_limit
        self.a = 0x0000
        self.x = 0x0000
        self.y = 0x0000
        self.s = 0x01FF
        self.d = 0x0000
        self.db = 0x00
        self.pb = 0x00
        self.pc = 0x0000
        self.m8 = True
        self.x8 = False
        self.c = False
        self.z = False
        self.n = False
        self.steps = 0

    def read8(self, address):
        return self.memory.read8(address & 0xFFFFFF) & 0xFF

    def write8(self, address, value):
        self.memory.write8(address & 0xFFFFFF, value & 0xFF)

    def read16(self, address):
        return self.read8(address) | (self.read8(address + 1) << 8)

    def fetch8(self):
        value = self.read8((self.pb << 16) | self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def fetch16(self):
        return self.fetch8() | (self.fetch8() << 8)

    def fetch24(self):
        return self.fetch16() | (self.fetch8() << 16)

    def push8(self, value):
        self.write8(self.s, value)
        self.s = (self.s - 1) & 0xFFFF

    def pull8(self):
        self.s = (self.s + 1) & 0xFFFF
        return self.read8(self.s)

    def push16(self, value):
        self.push8((value >> 8) & 0xFF)
        self.push8(value & 0xFF)

    def pull16(self):
        return self.pull8() | (self.pull8() << 8)

    def status(self):
        return (
            (0x20 if self.m8 else 0)
            | (0x10 if self.x8 else 0)
            | (0x01 if self.c else 0)
            | (0x02 if self.z else 0)
            | (0x80 if self.n else 0)
        )

    def set_status(self, value):
        self.m8 = bool(value & 0x20)
        self.x8 = bool(value & 0x10)
        self.c = bool(value & 0x01)
        self.z = bool(value & 0x02)
        self.n = bool(value & 0x80)

    def set_nz(self, value, wide):
        mask = 0xFFFF if wide else 0xFF
        self.z = (value & mask) == 0
        self.n = bool(value & (0x8000 if wide else 0x80))

    def load_a(self, value):
        if self.m8:
            self.a = (self.a & 0xFF00) | (value & 0xFF)
        else:
            self.a = value & 0xFFFF
        self.set_nz(value, not self.m8)

    def acc(self):
        return self.a & 0xFF if self.m8 else self.a

    def index(self, value):
        return value & 0xFF if not self.x8 else value & 0xFFFF

    def call(self, address):
        self.pb = (address >> 16) & 0xFF
        self.pc = address & 0xFFFF
        depth = 0
        while True:
            self.steps += 1
            if self.steps > self.step_limit:
                raise StepLimit(f"stopped after {self.steps} steps at ${self.pb:02X}:{self.pc:04X}")
            opcode = self.fetch8()
            if opcode in (0x6B, 0x60):
                if depth == 0:
                    return self
                depth -= 1
                continue
            if opcode == 0x22:
                target = self.fetch24()
                depth += 1
                self.pb = (target >> 16) & 0xFF
                self.pc = target & 0xFFFF
                continue
            self.execute(opcode)

    def execute(self, opcode):
        if opcode == 0xEA:
            return
        if opcode == 0xC2:
            self.set_status(self.status() & ~self.fetch8())
            return
        if opcode == 0xE2:
            self.set_status(self.status() | self.fetch8())
            return
        if opcode == 0x18:
            self.c = False
            return
        if opcode == 0x38:
            self.c = True
            return
        if opcode == 0x08:
            self.push8(self.status())
            return
        if opcode == 0x28:
            self.set_status(self.pull8())
            return
        if opcode == 0x8B:
            self.push8(self.db)
            return
        if opcode == 0xAB:
            self.db = self.pull8()
            return
        if opcode == 0xF4:
            self.push16(self.fetch16())
            return
        if opcode == 0x48:
            self.push8(self.a & 0xFF) if self.m8 else self.push16(self.a)
            return
        if opcode == 0x68:
            self.load_a(self.pull8() if self.m8 else self.pull16())
            return
        if opcode == 0xDA:
            self.push8(self.x & 0xFF) if self.x8 else self.push16(self.x)
            return
        if opcode == 0xFA:
            self.x = self.pull8() if self.x8 else self.pull16()
            return
        if opcode == 0x5A:
            self.push8(self.y & 0xFF) if self.x8 else self.push16(self.y)
            return
        if opcode == 0x7A:
            self.y = self.pull8() if self.x8 else self.pull16()
            return
        if opcode == 0xA8:
            self.y = self.acc() if not self.x8 else self.a & 0xFF
            return
        if opcode == 0xAA:
            self.x = self.acc() if not self.x8 else self.a & 0xFF
            return
        if opcode == 0xBB:
            self.x = self.y
            return
        if opcode == 0x98:
            self.load_a(self.y)
            return
        if opcode == 0xC8:
            self.y = (self.y + 1) & (0xFF if self.x8 else 0xFFFF)
            return
        if opcode == 0xE8:
            self.x = (self.x + 1) & (0xFF if self.x8 else 0xFFFF)
            return
        if opcode == 0xA9:
            self.load_a(self.fetch8() if self.m8 else self.fetch16())
            return
        if opcode == 0xA2:
            self.x = self.fetch8() if self.x8 else self.fetch16()
            return
        if opcode == 0xA0:
            self.y = self.fetch8() if self.x8 else self.fetch16()
            return
        if opcode == 0x29:
            self.load_a(self.acc() & (self.fetch8() if self.m8 else self.fetch16()))
            return
        if opcode == 0xAF:
            self.load_a(self.read_width(self.fetch24()))
            return
        if opcode == 0xBF:
            self.load_a(self.read_width(self.fetch24() + self.x))
            return
        if opcode == 0x8F:
            self.write_width(self.fetch24())
            return
        if opcode == 0x9F:
            self.write_width(self.fetch24() + self.x)
            return
        if opcode == 0xAD:
            self.load_a(self.read_width((self.db << 16) + self.fetch16()))
            return
        if opcode == 0xBD:
            self.load_a(self.read_width((self.db << 16) + self.fetch16() + self.x))
            return
        if opcode == 0xB9:
            self.load_a(self.read_width((self.db << 16) + self.fetch16() + self.y))
            return
        if opcode == 0x8D:
            self.write_width((self.db << 16) + self.fetch16())
            return
        if opcode == 0x9D:
            self.write_width((self.db << 16) + self.fetch16() + self.x)
            return
        if opcode == 0x99:
            self.write_width((self.db << 16) + self.fetch16() + self.y)
            return
        if opcode == 0xA5:
            self.load_a(self.read_width(self.d + self.fetch8()))
            return
        if opcode == 0x85:
            self.write_width(self.d + self.fetch8())
            return
        if opcode == 0xA3:
            self.load_a(self.read_width(self.s + self.fetch8()))
            return
        if opcode == 0xA6:
            self.x = self.read_index(self.d + self.fetch8())
            return
        if opcode == 0xAE:
            self.x = self.read_index((self.db << 16) + self.fetch16())
            return
        if opcode == 0xAC:
            self.y = self.read_index((self.db << 16) + self.fetch16())
            return
        if opcode == 0xA4:
            self.y = self.read_index(self.d + self.fetch8())
            return
        if opcode == 0xC9:
            self.compare(self.acc(), self.fetch8() if self.m8 else self.fetch16())
            return
        if opcode == 0xD9:
            self.compare(self.acc(), self.read_width((self.db << 16) + self.fetch16() + self.y))
            return
        if opcode == 0xDD:
            self.compare(self.acc(), self.read_width((self.db << 16) + self.fetch16() + self.x))
            return
        if opcode == 0xCD:
            self.compare(self.acc(), self.read_width((self.db << 16) + self.fetch16()))
            return
        if opcode == 0x80:
            self.branch(True)
            return
        if opcode == 0xF0:
            self.branch(self.z)
            return
        if opcode == 0xD0:
            self.branch(not self.z)
            return
        if opcode == 0x90:
            self.branch(not self.c)
            return
        if opcode == 0xB0:
            self.branch(self.c)
            return
        raise Unsupported(f"opcode {opcode:#04x} at ${self.pb:02X}:{(self.pc - 1) & 0xFFFF:04X}")

    def read_width(self, address):
        return self.read8(address) if self.m8 else self.read16(address)

    def read_index(self, address):
        return self.read8(address) if self.x8 else self.read16(address)

    def write_width(self, address):
        self.write8(address, self.a & 0xFF)
        if not self.m8:
            self.write8(address + 1, (self.a >> 8) & 0xFF)

    def compare(self, left, right):
        self.c = left >= right
        self.set_nz((left - right) & 0xFFFF, not self.m8)

    def branch(self, taken):
        offset = self.fetch8()
        if not taken:
            return
        if offset >= 0x80:
            offset -= 0x100
        self.pc = (self.pc + offset) & 0xFFFF
