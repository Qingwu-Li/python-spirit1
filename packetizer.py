import spi
s = spi.SPI('/dev/spidev32765.0', 0, 100000)
from bitarray import bitarray
r = []
ct = 0
from rle import *
import statistics
import base64
import time

printer = lambda xs: ''.join([{0: '▁', 1: '█'}[x] for x in xs])

def packetizer(xs):
    counts = sorted([x[0] for x in xs if x[1]])
    decile = len(counts)//10
    short_decile = statistics.mean(counts[1*decile:2*decile])
    long_decile = statistics.mean(counts[8*decile:9*decile])
    #print('first counts', short_decile, long_decile)
    #print([x for x in rle(counts)])
    breaks = [i[0] for i in enumerate(xs) if (i[1][0] > short_decile  * 4) and (i[1][1] == False)]
    break_deltas = [y-x for (x,y) in zip(breaks, breaks[1::])]
    try:
        mode = statistics.mode(break_deltas)
    except statistics.StatisticsError:
        mode = round(statistics.mean(break_deltas))
    #print(round(max(breaks) // mode))
    #print(breaks)
    breaks = [x*mode for x in range(round(max(breaks) // mode) + 2)]
    if breaks and breaks[0] != 0:
        breaks.insert(0,0)
    for (x,y) in zip(breaks, breaks[1::]):
        packet = xs[x+1:y]
        pb = []
        for chip in zip(packet[::2], packet[1::2]):
            if abs(chip[0][0] - short_decile) > abs(chip[0][0] - long_decile):
                pb += [1]
            else:
                pb += [0]
        print(len(pb), printer(pb))
    #print('breaks', breaks)


ba = bitarray(endian='big')

log = open(str(int(time.time()))+'.bitstreams.log', 'wb')

# block size
bs = 16834
while True:
    p = s.transfer([0]*bs)
    if p not in [[255]*bs, [0]*bs]:
        log.write(base64.b64encode(bytes(p))+b'\r\n')
        log.flush()
        ba.frombytes(bytes(p))
        packetizer([x for x in rle(ba)])
        ba = bitarray(endian='big')
