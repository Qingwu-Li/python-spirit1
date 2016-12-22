import spi
s = spi.SPI('/dev/spidev32765.0', 0, 100000)
from bitarray import bitarray
r = []
ct = 0
from rle import *
from statistics import mode, mean, StatisticsError
import base64
import time

printer = lambda xs: ''.join([{0: '░', 1: '█', 2: '╳'}[x] for x in xs])

def packetizer(xs):
    # drop short (clearly erroneous, spurious) pulses
    xs = [x for x in rle(rld([x for x in xs if x[0] > 2]))]
    # sort pulse widths
    counts_1 = sorted([x[0] for x in xs if x[1]])
    counts_0 = sorted([x[0] for x in xs if not x[1]])
    print('high', [x for x in rle(counts_1) if x[0] > 1 ])
    print('low', [x for x in rle(counts_0) if x[0] > 1 ])
    decile_1 = len(counts_1)//10
    decile_0 = len(counts_0)//10
    if (not decile_0) or (not decile_1):
        return (None, 'not enough data to derive decile')
    # find short and long segments
    short_decile_0 = mean(counts_0[1*decile_0:2*decile_0])
    long_decile_0 = mean(counts_0[8*decile_0:9*decile_0])
    short_decile_1 = mean(counts_1[1*decile_1:2*decile_1])
    long_decile_1 = mean(counts_1[8*decile_1:9*decile_1])
    # find segments of quiet that are 9x longer than the short period
    breaks = [i[0] for i in enumerate(xs) if (i[1][0] > min(short_decile_0,short_decile_1)  * 9) and (i[1][1] == False)]
    # find periodicity of the packets
    break_deltas = [y-x for (x,y) in zip(breaks, breaks[1::])]
    print('break_deltas', break_deltas)
    if len(break_deltas) < 2:
        return (None, 'no breaks detected')
    elif len(set(break_deltas)) > 3:
        try:
            d_mode = mode(break_deltas)
        # if all values different, use mean as mode
        except StatisticsError:
            d_mode = round(mean(break_deltas))
        # determine expected periodicity of packet widths
        breaks2 = [x*d_mode for x in range(round(max(breaks) // d_mode))]
        if len(breaks2) < 2:
            return (None, 'no packets')
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
            if (chip[1] == True) and (abs(chip[0] - short_decile_1) < short_decile_1 // 2):
                pb += [1]
            elif (chip[1] == False) and (abs(chip[0] - short_decile_0) < short_decile_0 // 2):
                pb += [0]
            # long pulse - 2 bitwidths of either high or low - if high, this is usually '1'
            elif (chip[1] == True) and (abs(chip[0] - long_decile_1) < long_decile_1 // 2):
                pb += [1,1]
            elif (chip[1] == False) and (abs(chip[0] - long_decile_0) < long_decile_0 // 2):
                pb += [0,0]
            # if pulse isn't nicely compartmentalized by the above, return an error
            else:
                errors += [chip]
                pb += [2]
        if len(pb) > 4:
            print(len(pb), printer(pb))
            if len(errors) > 0:
                print('temporal quantification errors', errors)
                print("doesn't fit into", ('short:', short_decile_0, short_decile_1), ('long:', long_decile_0, long_decile_1))
    return ('breaks', breaks)


ba = bitarray(endian='big')


# block size
bs = 32768
while True:
    p = s.transfer([0]*bs)
    # if input values are all-high or all-low
    ba = bitarray(endian='big')
    if p not in [[255]*bs, [0]*bs]:
        current_time = time.time()
        log = open(str(int(current_time))+'.bitstreams.log', 'wb')
        log.write(base64.b64encode(bytes(p))+b'\r\n')
        log.close()
        ba.frombytes(bytes(p))
        print(current_time, packetizer([x for x in rle(ba)]))
