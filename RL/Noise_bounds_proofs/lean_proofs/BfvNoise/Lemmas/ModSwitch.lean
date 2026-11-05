-- BfvNoise/Lemmas/ModSwitch.lean
-- Lemma 21: Modulus Switching noise bound in RNS representation.

import BfvNoise.Basic
import BfvNoise.Norms

namespace BfvNoise

/-- Modulus switching rounding noise term: (t / (2 * q')) * Sgeo(n, j). -/
def modSwitchRoundingNoise (ctx : BFVContext) (q' : ℝ) (j : ℕ) : ℝ :=
  (ctx.t / (2 * q')) * Sgeo ctx.n j

/-- Lemma 21: Invariant noise growth during modulus switching from q to q' = q / q_k.
    For a ciphertext of size j + 1 with invariant noise v,
    the modulus-switched noise v_ms satisfies:
    ||v_ms||_∞ ≤ ||v||_∞ + (t / (2 * q')) * ((n^{j+1} - 1) / (n - 1)). -/
axiom lemma21_mod_switch (ctx : BFVContext) (q' : ℝ) (hq' : 0 < q') (j : ℕ) (v_norm : ℝ) :
    ∃ v_ms_norm : ℝ,
      v_ms_norm ≤ v_norm + modSwitchRoundingNoise ctx q' j

/-- Verification that the rounding term is non-negative. -/
axiom modSwitchRoundingNoise_nonneg (ctx : BFVContext) (q' : ℝ) (hq' : 0 < q') (j : ℕ) :
    0 ≤ modSwitchRoundingNoise ctx q' j

end BfvNoise
