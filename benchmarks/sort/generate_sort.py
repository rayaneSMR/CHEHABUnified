"""Write fhe_io_example.txt for sort_<slot_count>: random inputs and the expected output.

The expected output evaluates the same decision tree as fhe() in sort.cpp
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

# fhe() of sort.cpp, one tree per supported size
TREES = {
    3: 'cond(c12, (cond(c23,o123,cond(c13, o132, o312))), (cond(c13,o213,cond(c23, o231, o321))) )',
    4: 'cond(c12, cond(c13, cond(c23, cond(c14, cond(c24, cond(c34, o1234, o1243), cond(c14, o1423, o4123) ), o1234 ), cond(c14, cond(c34, cond(c24, o1324, o1342), cond(c14, o1432, o4132) ), o1324 ) ), cond(c34, cond(c14, cond(c24, o3124, o3142), cond(c34, o3412, o4312) ), o3124 ) ), cond(c23, cond(c13, cond(c24, cond(c14, cond(c34, o2134, o2143), cond(c24, o2413, o4213) ), o2134 ), cond(c24, cond(c34, cond(c14, o2314, o2341), cond(c24, o2431, o4231) ), o2314 ) ), cond(c34, cond(c24, cond(c14, o3214, o3241), cond(c34, o3421, o4321) ), o3214 ) ) )',
}
if n not in TREES:
    raise SystemExit(f"sort: unsupported slot_count {n} (supported: {sorted(TREES)})")


def cond(c, a, b):
    return c * a + (1 - c) * b


# Inputs declared by fhe(): the comparison bits c_ij (i < j), c_ij = 1 if v_i <= v_j, and one
# input per permutation o<perm> holding the permutation itself as a number (e.g. o213 = 213)
values = rng.sample(range(1, 100), 4)
env = {}
for i, j in itertools.combinations(range(1, 5), 2):
    env[f"c{i}{j}"] = int(values[i - 1] <= values[j - 1])
perms = ["".join(p) for k in (3, 4) for p in itertools.permutations("1234"[:k])]
for p in perms:
    env[f"o{p}"] = int(p)
env["cond"] = cond
expected = eval(TREES[n], {"__builtins__": {}}, env)

names = [f"c{i}{j}" for i, j in itertools.combinations(range(1, 5), 2)] + [f"o{p}" for p in perms]
with open("fhe_io_example.txt", "w") as f:
    f.write(f"1 {len(names)} 1\n")
    for name in names:
        f.write(f"{name} 1 0 {env[name]}\n")
    f.write(f"output 1 {expected}\n")
