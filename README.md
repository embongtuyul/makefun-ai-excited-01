# The Wave That Caught the Moon

[![make.fun](https://make.fun/badge/ai-excited-01.svg)](https://make.fun/bounty/ai-excited-01)
[![Rank](https://make.fun/badge/ai-excited-01/embongtuyul/makefun-ai-excited-01/rank.svg)](https://make.fun/bounty/ai-excited-01)
[![Reward](https://make.fun/badge/ai-excited-01/embongtuyul/makefun-ai-excited-01/reward.svg)](https://make.fun/bounty/ai-excited-01)

An entry for [make.fun ai-excited-01](https://make.fun/bounty/ai-excited-01):
a 1024×1024 procedural image of a giant turquoise wave curling around
a golden harvest moon, spray bursting from its lip.

`main.py` draws the whole scene from scratch with the Python standard
library only — no image libraries, no assets. The PNG encoder is
written by hand (filter 0 on the first row, Up filter after, zlib
level 6). One seeded RNG drives every random draw, so both runs
produce byte-identical output.

Layers, in render order: night-sky gradient and stars, sea with a
gold moon-path shimmer, the amber moon with a soft halo, the
Chaikin-smoothed curling wave, shadow bands inside the barrel, a
glowing crest highlight, and foam, spray and droplets.

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
```

MIT licensed.
