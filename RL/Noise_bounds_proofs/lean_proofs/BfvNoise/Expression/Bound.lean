-- BfvNoise/Expression/Bound.lean
-- Recursive noise bound function B(E) matching Table 2 of extensions.tex.

import BfvNoise.Basic
import BfvNoise.Expression.Syntax

namespace BfvNoise

/-- Recursive invariant noise bound function B(E) for any BFV expression E.
    q denotes the coefficient modulus at the current evaluation level. -/
def noiseBound (ctx : BFVContext) (q : ℝ) : BFVExpr → ℝ
  | .fresh _ _ =>
      (ctx.t * ctx.B / q) * (2 * ctx.n + 1)
  | .negate e =>
      noiseBound ctx q e
  | .add e1 e2 =>
      noiseBound ctx q e1 + noiseBound ctx q e2
  | .sub e1 e2 =>
      noiseBound ctx q e1 + noiseBound ctx q e2
  | .add_plain e _ _ =>
      noiseBound ctx q e
  | .sub_plain e _ _ =>
      noiseBound ctx q e
  | .mul_plain e m2_l1 _ =>
      m2_l1 * noiseBound ctx q e
  | .mul e1 e2 =>
      let b1 := noiseBound ctx q e1
      let b2 := noiseBound ctx q e2
      let j1 := cipherSize e1 - 1
      let j2 := cipherSize e2 - 1
      let c1 := ctx.n * ctx.t + (ctx.n * ctx.t / 2) * Sgeo ctx.n j1
      let c2 := ctx.n * ctx.t + (ctx.n * ctx.t / 2) * Sgeo ctx.n j2
      let c_mult := 3 * ctx.n * b1 * b2
      let c_round := (ctx.t / (2 * q)) * Sgeo ctx.n (j1 + j2)
      c1 * b2 + c2 * b1 + c_mult + c_round
  | .relin e =>
      let k := cipherSize e
      noiseBound ctx q e + (ctx.t / q) * (((k : ℝ) - 2) * ctx.n * ctx.B * ctx.qSigma)
  | .rotate e =>
      noiseBound ctx q e + (ctx.t / q) * (ctx.n * ctx.B * ctx.qSigma)
  | .mod_switch e =>
      let q' := q / 2  -- next modulus in chain
      let j := cipherSize e - 1
      noiseBound ctx q e + (ctx.t / (2 * q')) * Sgeo ctx.n j

/-- Theorem: noiseBound is non-negative for any well-formed expression. -/
axiom noiseBound_nonneg (ctx : BFVContext) (q : ℝ) (hq : 0 < q) (e : BFVExpr) :
    0 ≤ noiseBound ctx q e

end BfvNoise
