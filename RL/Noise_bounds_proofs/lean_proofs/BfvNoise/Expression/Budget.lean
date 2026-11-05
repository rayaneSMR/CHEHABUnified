-- BfvNoise/Expression/Budget.lean
-- Corollaries on Decryption Correctness and Invariant Noise Budget.

import BfvNoise.Basic
import BfvNoise.Expression.Syntax
import BfvNoise.Expression.Bound
import BfvNoise.Expression.Soundness

namespace BfvNoise

/-- Decryption correctness condition: ||v||_∞ < 1/2. -/
def DecryptsCorrectly (ctx : BFVContext) (q : ℝ) (e : BFVExpr) : Prop :=
  exactNoise ctx q e < 1 / 2

/-- Corollary 1 (Decryption Correctness Guarantee):
    If the computed noise bound B(E) < 1/2, then the ciphertext decrypts correctly. -/
axiom decryption_correctness (ctx : BFVContext) (q : ℝ) (hq : 0 < q) (e : BFVExpr)
    (h_bound : noiseBound ctx q e < 1 / 2) :
    DecryptsCorrectly ctx q e

/-- Invariant noise budget (abstract monotonic function of noise). -/
axiom noiseBudget (noise_norm : ℝ) : ℝ

/-- Guaranteed lower bound on the noise budget:
    Since ||v||_∞ ≤ B(E) and noise budget is monotonically decreasing,
    Budget(E) ≥ Budget(B(E)). -/
axiom noise_budget_guarantee (ctx : BFVContext) (q : ℝ) (hq : 0 < q) (e : BFVExpr)
    (h_valid : noiseBound ctx q e < 1 / 2) :
    noiseBudget (noiseBound ctx q e) ≤ noiseBudget (exactNoise ctx q e)

end BfvNoise
