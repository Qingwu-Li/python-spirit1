import spidev
s1 = spidev.SpiDev()
s1.open(32765, 0)
s1.max_speed_hz = 20000
from bitarray import bitarray
r = []
ct = 0
from rle import *
import statistics
import base64
import time

printer = lambda xs: ''.join([{0: '▁', 1: '█'}[x] for x in xs])

def packetizer(xs):
    counts = sorted([x[0] for x in xs])
    deltas = [y-x for (x,y) in zip(counts, counts[1::])]
    median = statistics.median_grouped([v[0] for v in xs]) 
    print(median, counts)
    print(deltas)
    breaks = [i[0] for i in enumerate(xs) if (i[1][0] > median * 3) and (i[1][1] == False)]
    if breaks and breaks[0] != 0:
        breaks.insert(0,0)
    for (x,y) in zip(breaks, breaks[1::]):
        packet = xs[x+1:y]
        pb = []
        ratios = []
        for chip in zip(packet[::2], packet[1::2]):
            ratios += [max(chip[0][0] // chip[1][0], chip[1][0] // chip[0][0])]
            if chip[0][0] > chip[1][0]:
                pb += [1]
            else:
                pb += [0]
        if packet and len(pb):
            print(len(pb), printer(pb))
            print(ratios)
            ratios = []
            #print(packet[0:2], packet[-2:])
    #print(breaks)


ba = bitarray(endian='big')

log = open(str(int(time.time()))+'.bitstreams.log', 'wb')

while True:
    p = s1.xfer2([0]*(63))
    if p not in [[255]*63, [0]*63]:
        r += p
    if p == [0]*63:
        ct += 1
    if ct > 4 and r:
        log.write(base64.b64encode(bytes(r))+b'\r\n')
        log.flush()
        ba.frombytes(bytes(r))
        packetizer([x for x in rle(ba)])
        ba = bitarray(endian='big')
        r = []
        ct = 0

