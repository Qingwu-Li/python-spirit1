from CHIP_IO import GPIO
import spidev
from time import sleep
import atexit
import spirit1_regs as s1r

index_of_closest = lambda lst, x: lst.index(sorted(lst, key=lambda y: abs(y-x))[0])
band_thresholds = [860166667, 430083334, 322562500, 161281250]

def calc_rate(rate):
    for DR_E in range(16):
        DR_M = (rate * 2**28 / 25e6) / (2**DR_E) - 256
        if (DR_M > 0) and ( DR_M < 256):
            break
    if (DR_M >= 0) and (DR_M < 256) and (DR_E >= 0) and (DR_E < 16):
        return int(DR_M), int(DR_E)
    else:
        return None, None


class SpiritOne(object):

    def __init__(self, crystal = 50e6, SRES = True):
        self.crystal = crystal
        self.spi = spidev.SpiDev()
        GPIO.cleanup()
        GPIO.setup('XIO-P7', GPIO.OUT)
        GPIO.output('XIO-P7', GPIO.HIGH)
        sleep(0.1)
        GPIO.output('XIO-P7', GPIO.LOW)
        self.spi.open(32766, 0)
        self.spi.mode = 0
        self.spi.max_speed_hz = 1000000
        sleep(0.005)
        if SRES:
            self.command(s1r.COMMAND_SRES)
            sleep(0.002)
        self.set_IF()
        atexit.register(self.cleanup)

    def command(self, command_byte):
        return self.spi.xfer2([0b10000000, command_byte])

    def read(self, start_register, count=1):
        return self.spi.xfer2([0b00000001, start_register] + [0x00] * count)

    def write(self, start_register, data):
        if type(data) == int:
            res = [0, start_register, data]
        if type(data) == list:
            res = [0, start_register] + data
        return self.spi.xfer2(res)

    def decode_MC(self, b0, b1):
        STATE = b1 >> 1
        states = {0x40: 'STANDBY', 0x36: 'SLEEP', 0x03: 'READY', 0x0F: 'LOCK', 0x33: 'RX', 0x5F: 'TX'}
        if STATE in states.keys():
            return states[STATE]

    def cleanup(self):
        self.spi.close()
        GPIO.cleanup()

    def get_f_base(self):
        SYNT = self.read(s1r.SYNT3_BASE, 4)[-4::]
        BS = SYNT[3] & 0b11
        # 6 = 900MHz, 12 = 400MHz, 16 = 300MHz, 32 = 150MHz
        self.band = {1: 6, 3: 12, 4: 16, 5: 32}[BS]
        SYNT = (SYNT[0] & 0x1f) << 21 | SYNT[1] << 13 | SYNT[2] << 5 | (SYNT[3] >> 3)
        # BS / 2 for low crystals ( no divider )
        F_base = self.crystal * (SYNT / 2**18) / (self.band)
        return F_base

    def set_f_base(self, base):
        self.band = [6, 12, 16, 32][index_of_closest(band_thresholds, base)]
        SYNT = base*self.band*2**18/self.crystal
        SYNT = int(SYNT)
        BS = {16: 4, 32: 5, 12: 3, 6: 1}[self.band]
        SYNT <<= 3
        SYNT |= BS
        return self.write(s1r.SYNT3_BASE, [(SYNT>>24)&0xFF, (SYNT>>16)&0xFF, (SYNT>>8)&0xFF, (SYNT)&0xFF])
        

    def set_IF(self):
        # set intermediate frequency based on self.crystal
        table = """0xB6 0xB6 480.469 24
0xAC 0xAC 480.143 25
0xA3 0xA3 480.306 26
0x3B 0xB6 480.469 48
0x36 0xAC 480.143 50
0x31 0xA3 480.140 52"""
        table = [row.split() for row in table.split('\n')]
        mapping = dict([(int(row[3])*1e6, (int(row[0],16), int(row[1],16), float(row[2]))) for row in table])
        # 50MHz row from datasheet: 0x36 0xAC 480.143 50
        self.write(s1r.IF_OFFSET_ANA_BASE, mapping[self.crystal][0])
        self.write(s1r.IF_OFFSET_DIG_BASE, mapping[self.crystal][1])

    def set_freq(self, freq):
        self.set_f_base(freq)
        self.set_SYNTH1(freq)

    def set_SYNTH1(self, freq):
        sc1 = self.read(s1r.SYNTH_CONFIG1_BASE, 1)[-1]
        # enable division by 2 for high freq clock
        sc1 |= 0x80
        # clear bottom bits
        sc1 &= 0xF0
        if freq < band_thresholds[index_of_closest(band_thresholds, freq)]:
            # enable VCO_L
            sc1 |= 1 << 2
        else:
            # enable VCO_H
            sc1 |= 1 << 1 
        self.write(s1r.SYNTH_CONFIG1_BASE, sc1)

    def set_channel_spacing(self, chspacing):
        chspace = max(min(int(chspacing/(self.crystal / 2**15)), 255), 0)
        return self.write(s1r.CHSPACE_BASE, chspace)

    def set_channel_num(self, chnum):
        chnum = max(min(int(chnum), 255), 0)
        return self.write(s1r.CHNUM_BASE, chspace)

    def set_TX_RND(self):
        pc1 = s1.read(s1r.PCKTCTRL1_BASE)[-1]
        # PN9 continuous stream
        pc1 |= s1r.PCKTCTRL1_TX_SOURCE_MASK
        s1.write(s1r.PCKTCTRL1_BASE, pc1)

    def set_MOD(self, mod=s1r.MOD0_CW, rate = 1e3):
        m0 = mod
        DR_M, DR_E = calc_rate(rate)
        m0 |= DR_E
        s1.write(s1r.MOD1_BASE, [DR_M, m0])


if __name__ == "__main__":
    s1 = SpiritOne()
    s1.set_freq(433.92e6)
    freq = s1.get_f_base()
    s1.set_TX_RND()
    s1.set_MOD(s1r.MOD0_MOD_TYPE_ASK, rate=300)
    s1.write(s1r.PA_POWER7_BASE, 0x1F)
    for i in range(10):
        print(s1.decode_MC(*s1.command(s1r.COMMAND_TX)))
        sleep(0.5)
        print(s1.decode_MC(*s1.command(s1r.COMMAND_SABORT)))
        s1.set_f_base(freq-i*10e3)
        sleep(0.5)
