from CHIP_IO import GPIO
import spidev
from time import sleep
import atexit
import spirit1_regs as s1r

class SpiritOne(object):
	def __init__(self):
		self.spi = spidev.SpiDev()
		GPIO.cleanup()
		GPIO.setup('XIO-P7', GPIO.OUT)
		GPIO.output('XIO-P7', GPIO.HIGH)
		sleep(0.1)
		GPIO.output('XIO-P7', GPIO.LOW)
		self.spi.open(32766,0)
		self.spi.mode = 0
		self.spi.max_speed_hz = 1000000
		sleep(0.005)
		atexit.register(self.cleanup)
	def command(self, command_byte):
		res = self.spi.xfer2([0b10000000, command_byte])
		sleep(0.002)
		return res
	def read(self, start_register, count = 1):
		return self.spi.xfer2([0b00000001, start_register]+[0x00]*count)
	def write(self, start_register, data):
		if type(data) == int:
			res = [0, start_register, data]
		if type(data) == list:
			res = [0, start_register] + data
		return self.spi.xfer2(res)
	def decode_MC(self, b0, b1):
		states = {0x40:'STANDBY', 0x36:'SLEEP', 0x03:'READY', 0x0F: 'LOCK', 0x33:'RX', 0x5F:'TX'}
		return states[b1>>1]
	def cleanup(self):
		self.spi.close()
		GPIO.cleanup()
	def get_f_base(self):
		SYNT = self.read(s1r.SYNT3_BASE, 4)[-4::]
		BS = SYNT[3]&0b11
		# 6 = 900MHz, 12 = 400MHz, 16 = 300MHz, 32 = 150MHz
		BS = {1:6, 3:12, 4:16, 5:32}[BS] 
		SYNT = (SYNT[0]&0x1f) << 21 | SYNT[1] << 13 | SYNT[2] << 5 | (SYNT[3]>>3)
		# constant per hardware design
		F_xo = 50e6 / 2
		F_base = F_xo * (SYNT/2**18) / (BS*1/2)
		return F_base
	def set_IF(self):
		# 50MHz row from datasheet: 0x36 0xAC 480.143 50
		self.write(s1r.IF_OFFSET_ANA_BASE, 0x36)
		self.write(s1r.IF_OFFSET_DIG_BASE, 0xAC)
	def set_SYNTH1(self):
		sc1 = self.read(s1r.SYNTH_CONFIG1_BASE, 1)[-1]
		# enable division by 2 for high freq clock
		sc1 |= 0x80
		# clear bottom bits
		sc1 &= 0xF0
		# enable VCO_L
		sc1 |= 1 << 2
		self.write(s1r.SYNTH_CONFIG1_BASE, sc1)
		

if __name__ == "__main__":
	s1 = SpiritOne()
	s1.command(s1r.COMMAND_SRES)
	print([hex(x) for x in s1.read(s1r.DEVICE_INFO1_PARTNUM, 2)])
	s1.set_IF()
	s1.set_SYNTH1()
	# PN9 continuous random data stream
	s1.write(s1r.PCKTCTRL1_BASE, s1.read(s1r.PCKTCTRL1_BASE)[-1]|s1r.PCKTCTRL1_TX_SOURCE_MASK)
	# no modulation - continuous wave (CW) bit high
	s1.write(s1r.MOD0_BASE, 0x80)
	s1.write(s1r.PA_POWER7_BASE, 0x1F)
	print(s1.get_f_base())
	print(s1.decode_MC(*s1.command(s1r.COMMAND_TX)))
	sleep(1)
	s1.command(s1r.COMMAND_SRES)

