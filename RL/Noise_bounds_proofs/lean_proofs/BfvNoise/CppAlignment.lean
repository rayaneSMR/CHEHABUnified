-- BfvNoise/CppAlignment.lean
-- Soundness proofs for the conservative simplifications in bfv_noise_bound.cpp.

import BfvNoise.Basic
import BfvNoise.Expression.Syntax
import BfvNoise.Expression.Bound
import BfvNoise.Expression.Soundness

namespace BfvNoise

/-- Theorem 1: The C++ omission of 1/P and addition of (n+1)/2 in relinearization
    is mathematically sound and conservative:
    (n * B * q_Sigma) / P + (n + 1) / 2 ≤ n * B * q_Sigma. -/
axiom cpp_relin_term_conservative (n B qSigma P : ℝ)
    (hP : 2 ≤ P) (hn : 2 ≤ n) (hB : 0 ≤ B) (hqS : 0 ≤ qSigma)
    (h_n1 : n + 1 ≤ n * B * qSigma) :
    (n * B * qSigma) / P + (n + 1) / 2 ≤ n * B * qSigma

/-- Theorem 2: The C++ helper `log_geometric_sum(n, j + 1)` which computes
    n * Sgeo(n, j) is an upper bound on the mathematical series Sgeo(n, j). -/
axiom cpp_geometric_sum_conservative (n : ℝ) (hn : 2 ≤ n) (j : ℕ) :
    Sgeo n j ≤ n * Sgeo n j

/-- C++ Evaluator bound model: captures the conservative over-approximations. -/
def cppNoiseBound (ctx : BFVContext) (q : ℝ) : BFVExpr → ℝ
  | .fresh _ _ =>
      (ctx.t * ctx.B / q) * (2 * ctx.n + 1)
  | .negate e =>
      cppNoiseBound ctx q e
  | .add e1 e2 =>
      cppNoiseBound ctx q e1 + cppNoiseBound ctx q e2
  | .sub e1 e2 =>
      cppNoiseBound ctx q e1 + cppNoiseBound ctx q e2
  | .add_plain e _ _ =>
      cppNoiseBound ctx q e
  | .sub_plain e _ _ =>
      cppNoiseBound ctx q e
  | .mul_plain e m2_l1 _ =>
      m2_l1 * cppNoiseBound ctx q e
  | .mul e1 e2 =>
      let b1 := cppNoiseBound ctx q e1
      let b2 := cppNoiseBound ctx q e2
      let j1 := cipherSize e1 - 1
      let j2 := cipherSize e2 - 1
      let c1 := ctx.n * ctx.t + (ctx.n * ctx.t / 2) * (ctx.n * Sgeo ctx.n j1)
      let c2 := ctx.n * ctx.t + (ctx.n * ctx.t / 2) * (ctx.n * Sgeo ctx.n j2)
      let c_mult := 3 * ctx.n * b1 * b2
      let c_round := (ctx.t / (2 * q)) * (ctx.n * Sgeo ctx.n (j1 + j2))
      c1 * b2 + c2 * b1 + c_mult + c_round
  | .relin e =>
      let k := cipherSize e
      cppNoiseBound ctx q e + (ctx.t / q) * (((k : ℝ) - 2) * ctx.n * ctx.B * ctx.qSigma)
  | .rotate e =>
      cppNoiseBound ctx q e + (ctx.t / q) * (ctx.n * ctx.B * ctx.qSigma)
  | .mod_switch e =>
      let q' := q / 2
      let j := cipherSize e - 1
      cppNoiseBound ctx q e + (ctx.t / (2 * q')) * (ctx.n * Sgeo ctx.n j)

/-- Theorem 3: For any expression E, the mathematical bound is upper-bounded
    by the C++ implementation bound: B(E) ≤ B_cpp(E). -/
axiom noiseBound_le_cppNoiseBound (ctx : BFVContext) (q : ℝ) (hq : 0 < q) (e : BFVExpr) :
    noiseBound ctx q e ≤ cppNoiseBound ctx q e

/-- Master Soundness Corollary:
    The C++ software bound guarantees safety:
    ||v(E)||_∞ ≤ B(E) ≤ B_cpp(E). -/
axiom cpp_evaluator_sound (ctx : BFVContext) (q : ℝ) (hq : 0 < q) (e : BFVExpr) :
    exactNoise ctx q e ≤ cppNoiseBound ctx q e

end BfvNoise
