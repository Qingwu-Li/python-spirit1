import spi
import time
import atexit
import spirit1_regs as s1r

from tinygpio import *

index_of_closest = lambda lst, x: lst.index(sorted(lst, key=lambda y: abs(y - x))[0])
band_thresholds = [860166667, 430083334, 322562500, 161281250]


try:
    # banana pi
    open('/etc/armbian-release')
    SDN = t_name('PI14')
except:
    # CHIP
    SDN = 1016 + 7

class SpiritOne(object):

    def __init__(self, crystal=50e6, reset=True):
        self.crystal = crystal
        self.spi = spi.SPI('/dev/spidev32766.0', 0, 1000000)
        atexit.register(self.cleanup)
        if reset:
            self.reset()

    def reset(self):
        try:
            t_export(SDN)
        except:
            pass
        t_output(SDN)
        t_high(SDN)
        time.sleep(0.1)
        t_low(SDN)
        time.sleep(0.005)
        self.command(s1r.COMMAND_SRES)
        time.sleep(0.002)
        self.set_IF()
        

    def calc_rate(self, rate):
        for DR_E in range(16):
            DR_M = (rate * 2**28 / (self.crystal / 2)) / (2**DR_E) - 256
            if (DR_M > 0) and (DR_M < 256):
                break
        if (DR_M >= 0) and (DR_M < 256) and (DR_E >= 0) and (DR_E < 16):
            return int(DR_M), int(DR_E)
        else:
            return None, None

    def command(self, command_byte):
        return self.spi.transfer([0b10000000, command_byte])

    def read(self, start_register, count=1):
        return self.spi.transfer([0b00000001, start_register] + [0x00] * count)

    def write(self, start_register, data):
        if type(data) == int:
            res = [0, start_register, data]
        if type(data) == list:
            res = [0, start_register] + data
        if type(data) == bytes:
            res = [0, start_register] + [x for x in data]
        return self.spi.transfer(res)

    def decode_MC(self, b0, b1):
        STATE = b1 >> 1
        states = {0x40: 'STANDBY', 0x36: 'SLEEP', 0x03: 'READY', 0x0F: 'LOCK', 0x33: 'RX', 0x5F: 'TX', 0x13: 'LOCKWON'}
        if STATE in states.keys():
            return states[STATE]

    def cleanup(self):
        self.spi.close()

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
        SYNT = base * self.band * 2**18 / self.crystal
        SYNT = int(SYNT)
        BS = {16: 4, 32: 5, 12: 3, 6: 1}[self.band]
        SYNT <<= 3
        SYNT |= BS
        out = SYNT.to_bytes(4, byteorder='big')
        return self.write(s1r.SYNT3_BASE, out)

    def set_IF(self):
        # set intermediate frequency based on self.crystal
        table = """0xB6 0xB6 480.469 24
0xAC 0xAC 480.143 25
0xA3 0xA3 480.306 26
0x3B 0xB6 480.469 48
0x36 0xAC 480.143 50
0x31 0xA3 480.140 52"""
        table = [row.split() for row in table.split('\n')]
        mapping = dict([(int(row[3]) * 1e6, (int(row[0], 16), int(row[1], 16), float(row[2]))) for row in table])
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
        chspace = max(min(int(chspacing / (self.crystal / 2**15)), 255), 0)
        return self.write(s1r.CHSPACE_BASE, chspace)

    def set_channel_num(self, chnum):
        chnum = max(min(int(chnum), 255), 0)
        return self.write(s1r.CHNUM_BASE, chspace)

    def set_TX_MODE(self, mode=s1r.PCKTCTRL1_TX_MODE_PN9):
        self.write(s1r.PCKTCTRL1_BASE, mode)

    def set_MOD(self, mod=s1r.MOD0_CW, rate=1e3):
        DR_M, DR_E = self.calc_rate(rate)
        m0 = mod | DR_E
        self.write(s1r.MOD1_BASE, [DR_M, m0])

    def set_max_channel_filter(self):
        self.write(s1r.CHFLT_BASE, 0x00)

    def set_no_AFC(self):
        self.write(s1r.AFC2_BASE, 0x00)

    def setup_RSSI(self, threshold = -78):
        # dynamic link quality sensing
        self.write(s1r.RSSI_FLT_BASE, [0xE4, 2*(threshold+130)])

    def setup_clockrec(self):
        #self.write(s1r.FDEV0_BASE, 1<<3)
        # reset values except use short preamble
        self.write(s1r.CLOCKREC_BASE, 0b01001000)

    def setup_AGC(self):
        # ASK requires long settling time
        # TAGCmeas = 12/F_clk * 2**MEAS_TIME
        # AGCCTRL2
        # 0xE -> 8ms
        # 0xD -> 4ms
        self.write(s1r.AGCCTRL2_BASE, 0xB)

    def set_RX_MODE(self, mode=s1r.PCKTCTRL3_RX_MODE_DIRECT_FIFO):
        self.write(s1r.PCKTCTRL3_BASE, mode)

    def set_no_SQI(self):
        self.write(s1r.QI_BASE, 0)

    def setup_RX(freq = 433.92e6):
        s1.set_freq(433.92e6)
        freq = s1.get_f_base()
        s1.set_max_channel_filter()
        s1.set_RX_MODE()
        s1.set_no_AFC()
        s1.setup_AGC()
        s1.setup_RSSI()
        s1.set_no_SQI()
        s1.setup_clockrec()
        s1.set_MOD(s1r.MOD0_MOD_TYPE_ASK, rate=1 / 0.000165)
        # enable carrier sense blanking
        s1.write(s1r.ANT_SELECT_CONF_BASE, 0b10000)
        return s1.decode_MC(*s1.command(s1r.COMMAND_RX))

if __name__ == "__main__":
    s1 = SpiritOne()
    last = 0
    while True:
        if (time.time() - last) > 600:
            s1.reset()
            print(s1.setup_RX())
            last = time.time()
            time.sleep(1)
        link_qual = s1.read(s1r.LINK_QUALIF1_BASE, 3)
        # call SABORT to update RSSI and AGC
        s1.decode_MC(*s1.command(s1r.COMMAND_SABORT))
        # call RX for sport
        s1.decode_MC(*s1.command(s1r.COMMAND_RX))
        s1.write(s1r.GPIO0_CONF_BASE, (16 << 3) | 0b11)
        # get count of bytes in FIFO
        fifo_len = s1.read(s1r.LINEAR_FIFO_STATUS0_BASE, 1)[-1]
        if fifo_len:
            res = s1.command(s1r.COMMAND_FLUSHRXFIFO)
            #print(bin(int().from_bytes(bytes(res[3::]), 'big')))
            print('RSSI', link_qual[-1]/2-130.)
        time.sleep(0.05)
