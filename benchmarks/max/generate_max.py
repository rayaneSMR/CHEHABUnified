"""Write fhe_io_example.txt for max_<slot_count>: random inputs and the expected output.

The expected output evaluates the same decision tree as fhe() in max.cpp
(copied below for each size), with cond(c, a, b) = c*a + (1 - c)*b.
"""
import argparse
import itertools
import random

parser = argparse.ArgumentParser(description="Get io_file generation parameters")
parser.add_argument("--slot_count", required=True, type=int, help="Slot_count")
parser.add_argument("--seed", type=int, default=None)
args = parser.parse_args()
n = args.slot_count
rng = random.Random(args.seed)

# fhe() of max.cpp, one tree per supported size
TREES = {
    3: 'cond(c12, cond(c13,o1,o3) , cond(c23,o2,o3))',
    4: 'cond( c12, cond(c13,cond(c14,o1,o4),cond(c34,o3,o4)), cond(c23,cond(c24,o2,o4),cond(c34,o3,o4)) )',
    5: 'cond(c12, (cond(c13, cond(c14,cond(c15, o1, o5),cond(c45, o4, o5)), cond(c34,cond(c35, o3, o5),cond(c45, o4, o5))) ), (cond(c23, cond(c24,cond(c25, o2, o5),cond(c45, o4, o5)), cond(c34, cond(c35, o3, o5), cond(c45, o4, o5))) ) )',
}
if n not in TREES:
    raise SystemExit(f"max: unsupported slot_count {n} (supported: {sorted(TREES)})")


def cond(c, a, b):
    return c * a + (1 - c) * b


# Inputs declared by fhe(): o1..o5 and the comparison bits c_ij (i < j), c_ij = 1 if o_i > o_j
values = rng.sample(range(2, 30), 5)
env = {f"o{i + 1}": v for i, v in enumerate(values)}
for i, j in itertools.combinations(range(1, 6), 2):
    env[f"c{i}{j}"] = int(values[i - 1] > values[j - 1])
env["cond"] = cond
expected = eval(TREES[n], {"__builtins__": {}}, env)

names = [f"o{i}" for i in range(1, 6)] + [f"c{i}{j}" for i, j in itertools.combinations(range(1, 6), 2)]
with open("fhe_io_example.txt", "w") as f:
    f.write(f"1 {len(names)} 1\n")
    for name in names:
        f.write(f"{name} 1 0 {env[name]}\n")
    f.write(f"output 1 {expected}\n")
