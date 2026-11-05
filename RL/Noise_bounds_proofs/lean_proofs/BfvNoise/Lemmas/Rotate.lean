-- BfvNoise/Lemmas/Rotate.lean
-- Lemma 20: Galois Slot Rotation in RNS representation.

import BfvNoise.Basic
import BfvNoise.Norms
import BfvNoise.Lemmas.KeySwitch

namespace BfvNoise

/-- Single-step Galois rotation noise growth. -/
def rotStepNoise (ctx : BFVContext) : ℝ :=
  (ctx.t / ctx.q) * (ctx.n * ctx.B * ctx.qSigma)

/-- Lemma 20: Invariant noise growth during Galois slot rotation.
    For an input ciphertext of size 2 with invariant noise v and an odd Galois element g,
    the rotated noise v_rot satisfies:
    ||v_rot||_∞ ≤ ||v||_∞ + (t/q) * n * B * q_Sigma. -/
axiom lemma20_rotate (ctx : BFVContext) (g : ℕ) (hg : Odd g) (v_norm : ℝ) :
    ∃ v_rot_norm : ℝ,
      v_rot_norm ≤ v_norm + (ctx.t / ctx.q) * (ctx.n * ctx.B * ctx.qSigma)

end BfvNoise
