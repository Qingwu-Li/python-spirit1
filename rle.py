import itertools as its

ilen = lambda it: sum(1 for _ in it)
rle = lambda xs: ((ilen(gp), x) for x, gp in its.groupby(xs))
rld = lambda xs: its.chain.from_iterable(its.repeat(x, n) for n, x in xs)
