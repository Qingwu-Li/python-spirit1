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
		res = self.spi.xfer2([0b10000001, command_byte])
		sleep(0.002)
		return res
	def read(self, start_register, count = 1):
		return self.spi.xfer2([0b00000001, start_register]+[0x00]*count)
	def cleanup(self):
		self.spi.close()
		GPIO.cleanup()

if __name__ == "__main__":
	s1 = SpiritOne()
	print([hex(x) for x in s1.read(s1r.DEVICE_INFO1_PARTNUM, 2)])
