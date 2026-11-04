"""The vectorization rules of RL/rules.txt must not change the value of any lane.

Applies every vectorize / flexible / rotation rule to random (Vec ...) expressions whose
lanes mix variables, (- a), (- a b), (+ a b) and (* a b), and checks that the original
lanes evaluate to the same values afterwards (rotation rules may add lanes after them).
"""
import random
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RL_DIR = REPO_ROOT / "RL"
sys.path.insert(0, str(RL_DIR))
sys.path.insert(0, str(RL_DIR / "pytrs"))

from pytrs import parse_sexpr                     # noqa: E402
from pytrs.util import evaluate_expr              # noqa: E402
from rule_parser import parse_rules_from_text     # noqa: E402

VECTORIZE_TYPES = ("vectorize", "vectorize-flexible", "vectorize-rotation", "vectorize-rotation-flexible")
VARS = ["a", "b", "c", "d", "e"]


def random_lane(rng):
    x, y = rng.choice(VARS), rng.choice(VARS)
    return rng.choice([x, f"(- {x})", f"(- {x} {y})", f"(+ {x} {y})", f"(* {x} {y})", "0"])


def lanes_of(value):
    return value if isinstance(value, list) else [value]


class TestVectorizeRulesSound(unittest.TestCase):
    def test_rules_keep_every_lane(self):
        rules = [r for r in parse_rules_from_text((RL_DIR / "rules.txt").read_text())
                 if r.rule_type in VECTORIZE_TYPES]
        self.assertTrue(rules, "no vectorize rules found in rules.txt")
        rng = random.Random(0)
        applied = {r.name: 0 for r in rules}
        for _ in range(3000):
            n = rng.choice([2, 3, 4, 5])
            text = "(Vec " + " ".join(random_lane(rng) for _ in range(n)) + ")"
            expr = parse_sexpr(text)
            envs = [{v: rng.randint(-9, 9) for v in VARS} for _ in range(3)]
            refs = [lanes_of(evaluate_expr(expr, env)) for env in envs]
            for rule in rules:
                out = rule.apply(expr)
                if out is None:
                    continue
                applied[rule.name] += 1
                for env, ref in zip(envs, refs):
                    full = lanes_of(evaluate_expr(out, env))
                    self.assertEqual(full[:len(ref)], ref, f"{rule.name} changed {text} into {out}")
                    if rule.rule_type in ("vectorize-rotation", "vectorize-rotation-flexible"):
                        # widened lanes must repeat the original ones (the compiler repeats
                        # a vector over the slots)
                        self.assertEqual(full[len(ref):2 * len(ref)], ref,
                                         f"{rule.name}: widened lanes differ in {out}")
        unused = [name for name, k in applied.items() if k == 0]
        print(f"vectorize rules checked: {applied}; never applicable: {unused}")

    def test_rotation_rules_skip_nested_vectors(self):
        """A rotation rule must not widen a vector combined with a shorter one (the max_3
        case: wrong SEAL outputs), but may widen the outermost vector."""
        rules = [r for r in parse_rules_from_text((RL_DIR / "rules.txt").read_text())
                 if r.rule_type in ("vectorize-rotation", "vectorize-rotation-flexible")]
        nested = parse_sexpr("(VecMul (Vec (+ a b) c) (Vec (- 1 c) (+ (* a d) e)))")
        top = parse_sexpr("(Vec (- 1 c) (+ (* a d) e))")
        for rule in rules:
            for path, _ in rule.find_matching_subexpressions(nested):
                self.fail(f"{rule.name} matched the nested vector at {path}")
        self.assertTrue(any(r.find_matching_subexpressions(top) for r in rules),
                        "no rotation rule matches the outermost vector any more")

    def test_pattern_rules_keep_value(self):
        """Every plain rewrite rule (rules.txt and rotations_rules.txt): instantiate its
        left-hand side with random vectors (vector rules) or scalars, apply, compare."""
        from expr import Op, Var     # same module as rule_parser (pytrs/ is on sys.path)
        text = (RL_DIR / "rules.txt").read_text() + "\n" + (RL_DIR / "rotations_rules.txt").read_text()
        rules = [r for r in parse_rules_from_text(text) if r.rule_type not in VECTORIZE_TYPES]
        self.assertTrue(rules)
        rng = random.Random(1)
        L = 8

        def has_vector_op(e):
            return isinstance(e, Op) and (e.op.startswith("Vec") or e.op == "<<"
                                          or any(has_vector_op(a) for a in e.args))

        def instantiate(e, subst, vector):
            if isinstance(e, Var):
                if e.name not in subst:
                    if vector:
                        subst[e.name] = Op("Vec", [Var(rng.choice(VARS)) for _ in range(L)])
                    else:
                        subst[e.name] = parse_sexpr(random_lane(rng))
                return subst[e.name]
            if isinstance(e, Op):
                return Op(e.op, [instantiate(a, subst, vector) for a in e.args])
            return e

        checked = 0
        for rule in rules:
            lhs = rule.lhs.expr
            vector = has_vector_op(lhs)
            for _ in range(20):
                expr = instantiate(lhs, {}, vector)
                out = rule.apply(expr)
                if out is None:
                    continue
                checked += 1
                for _ in range(3):
                    env = {v: rng.randint(-9, 9) for v in VARS}
                    self.assertEqual(lanes_of(evaluate_expr(out, env)), lanes_of(evaluate_expr(expr, env)),
                                     f"{rule.name} changed {expr} into {out}")
        print(f"plain rules: {len(rules)}, applications checked: {checked}")


if __name__ == "__main__":
    unittest.main()
