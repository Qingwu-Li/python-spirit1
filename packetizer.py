import spi
s = spi.SPI('/dev/spidev32765.0', 0, 100000)
from bitarray import bitarray
r = []
ct = 0
from rle import *
import statistics
import base64
import time

printer = lambda xs: ''.join([{0: '░', 1: '█', 2: '╳'}[x] for x in xs])

def packetizer(xs):
    # drop short (clearly erroneous, spurious) pulses
    xs = [x for x in rle(rld([x for x in xs if x[0] > 2]))]
    # sort pulse widths
    counts = sorted([x[0] for x in xs if x[1]])
    decile = len(counts)//10
    if not decile:
        return None
    # find short and long segments
    short_decile = statistics.mean(counts[1*decile:2*decile])
    long_decile = statistics.mean(counts[8*decile:9*decile])
    # find segments of quiet that are 9x longer than the short period
    breaks = [i[0] for i in enumerate(xs) if (i[1][0] > short_decile  * 9) and (i[1][1] == False)]
    # find periodicity of the packets
    break_deltas = [y-x for (x,y) in zip(breaks, breaks[1::])]
    if len(break_deltas) < 2:
        return None
    try:
        mode = statistics.mode(break_deltas)
    # if all values different, use mean as mode
    except statistics.StatisticsError:
        mode = round(statistics.mean(break_deltas))
    # determine expected periodicity of packet widths
    breaks2 = [x*mode for x in range(round(max(breaks) // mode))]
    if len(breaks2) < 2:
        return None
    # discard breaks more than 10% from expected position
    breaks = [x for x in breaks if True in [abs(x-y) < breaks2[1]//10 for y in breaks2]]
    # define packet pulses as the segment between breaks
    for (x,y) in zip(breaks, breaks[1::]):
        packet = xs[x+1:y]
        pb = []
        errors = []
        # iterate over packet pulses
        for chip in packet:
            # short pulse - 1 bitwidth of either high or low - if high, this is usually '0' 
            if (abs(chip[0] - short_decile) < short_decile // 2):
                if chip[1] == True:
                    pb += [1]
                else:
                    pb += [0]
            # long pulse - 2 bitwidths of either high or low - if high, this is usually '1'
            elif abs(chip[0] - long_decile) < long_decile // 2:
                if chip[1] == True:
                    pb += [1,1]
                else:
                    pb += [0,0]
            # if pulse isn't nicely compartmentalized by the above, return an error
            else:
                errors += [chip]
                pb += [2]
        if len(pb):
            print(len(pb), printer(pb))
            print(errors)
    #print('breaks', breaks)


ba = bitarray(endian='big')

log = open(str(int(time.time()))+'.bitstreams.log', 'wb')

# block size
bs = 32768
while True:
    p = s.transfer([0]*bs)
    # if input values are all-high or all-low
    if p not in [[255]*bs, [0]*bs]:
        log.write(base64.b64encode(bytes(p))+b'\r\n')
        log.flush()
        ba.frombytes(bytes(p))
        packetizer([x for x in rle(ba)])
        ba = bitarray(endian='big')
