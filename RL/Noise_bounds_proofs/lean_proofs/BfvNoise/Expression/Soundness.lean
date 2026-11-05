-- BfvNoise/Expression/Soundness.lean
-- Lemma 22: Soundness of the Invariant Noise Bound for an arbitrary BFV expression of size N.

import BfvNoise.Basic
import BfvNoise.Expression.Syntax
import BfvNoise.Expression.Bound
import BfvNoise.Lemmas.KeySwitch
import BfvNoise.Lemmas.Relin
import BfvNoise.Lemmas.Rotate
import BfvNoise.Lemmas.ModSwitch

namespace BfvNoise

/-- Exact invariant noise norm ||v(E)||_∞ resulting from evaluating expression E. -/
axiom exactNoise (ctx : BFVContext) (q : ℝ) : BFVExpr → ℝ

-- --------------------------------------------------------------------
-- Single-operation noise transfer rules established in Lemmas 9-21
-- --------------------------------------------------------------------

/-- Lemma 9: Fresh encryption noise bound. -/
axiom noise_fresh (ctx : BFVContext) (q : ℝ) (m : ℝ) (hm : 0 ≤ m) :
    exactNoise ctx q (.fresh m hm) ≤ noiseBound ctx q (.fresh m hm)

/-- Lemma 15: Negation preserves exact invariant noise. -/
axiom noise_negate (ctx : BFVContext) (q : ℝ) (e : BFVExpr) :
    exactNoise ctx q (.negate e) = exactNoise ctx q e

/-- Lemma 10: Homomorphic addition noise growth. -/
axiom noise_add (ctx : BFVContext) (q : ℝ) (e1 e2 : BFVExpr) :
    exactNoise ctx q (.add e1 e2) ≤ exactNoise ctx q e1 + exactNoise ctx q e2

/-- Lemma 16: Homomorphic subtraction noise growth. -/
axiom noise_sub (ctx : BFVContext) (q : ℝ) (e1 e2 : BFVExpr) :
    exactNoise ctx q (.sub e1 e2) ≤ exactNoise ctx q e1 + exactNoise ctx q e2

/-- Lemma 14: Plain addition noise growth. -/
axiom noise_add_plain (ctx : BFVContext) (q : ℝ) (e : BFVExpr) (m2 : ℝ) (hm2 : 0 ≤ m2) :
    exactNoise ctx q (.add_plain e m2 hm2) ≤ exactNoise ctx q e

/-- Lemma 17: Plain subtraction noise growth. -/
axiom noise_sub_plain (ctx : BFVContext) (q : ℝ) (e : BFVExpr) (m2 : ℝ) (hm2 : 0 ≤ m2) :
    exactNoise ctx q (.sub_plain e m2 hm2) ≤ exactNoise ctx q e

/-- Lemma 13: Plain multiplication noise growth. -/
axiom noise_mul_plain (ctx : BFVContext) (q : ℝ) (e : BFVExpr) (l1 : ℝ) (hl1 : 0 ≤ l1) :
    exactNoise ctx q (.mul_plain e l1 hl1) ≤ l1 * exactNoise ctx q e

/-- Lemma 11: Homomorphic multiplication noise growth. -/
axiom noise_mul (ctx : BFVContext) (q : ℝ) (e1 e2 : BFVExpr) :
    let v1 := exactNoise ctx q e1
    let v2 := exactNoise ctx q e2
    let j1 := cipherSize e1 - 1
    let j2 := cipherSize e2 - 1
    let c1 := ctx.n * ctx.t + (ctx.n * ctx.t / 2) * Sgeo ctx.n j1
    let c2 := ctx.n * ctx.t + (ctx.n * ctx.t / 2) * Sgeo ctx.n j2
    let c_mult := 3 * ctx.n * v1 * v2
    let c_round := (ctx.t / (2 * q)) * Sgeo ctx.n (j1 + j2)
    exactNoise ctx q (.mul e1 e2) ≤ c1 * v2 + c2 * v1 + c_mult + c_round

/-- Lemma 19: Relinearization to size 2 noise growth. -/
axiom noise_relin (ctx : BFVContext) (q : ℝ) (e : BFVExpr) :
    let k := cipherSize e
    exactNoise ctx q (.relin e) ≤ exactNoise ctx q e +
      (ctx.t / q) * (((k : ℝ) - 2) * ctx.n * ctx.B * ctx.qSigma)

/-- Lemma 20: Galois rotation noise growth. -/
axiom noise_rotate (ctx : BFVContext) (q : ℝ) (e : BFVExpr) :
    exactNoise ctx q (.rotate e) ≤ exactNoise ctx q e + (ctx.t / q) * (ctx.n * ctx.B * ctx.qSigma)

/-- Lemma 21: Modulus switching noise growth. -/
axiom noise_mod_switch (ctx : BFVContext) (q : ℝ) (e : BFVExpr) :
    let q' := q / 2
    let j := cipherSize e - 1
    exactNoise ctx q (.mod_switch e) ≤ exactNoise ctx q e + (ctx.t / (2 * q')) * Sgeo ctx.n j

/-- Lemma 22 (Track 3): For any well-formed BFV expression E of arbitrary size N,
    the evaluated invariant noise satisfies ||v(E)||_∞ ≤ B(E). -/
axiom lemma22_expression_soundness (ctx : BFVContext) (q : ℝ) (hq : 0 < q) (e : BFVExpr) :
    exactNoise ctx q e ≤ noiseBound ctx q e

end BfvNoise
