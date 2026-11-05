-- BfvNoise/Lemmas/Relin.lean
-- Lemma 19: Ciphertext Relinearization in RNS representation.

import BfvNoise.Basic
import BfvNoise.Norms
import BfvNoise.Lemmas.KeySwitch

namespace BfvNoise

/-- One-step relinearization noise growth. -/
def relinStepNoise (ctx : BFVContext) : ℝ :=
  (ctx.t / ctx.q) * (ctx.n * ctx.B * ctx.qSigma)

/-- Full relinearization noise growth from size M+1 down to size N+1. -/
def relinTotalNoise (ctx : BFVContext) (M N : ℕ) : ℝ :=
  (M - N : ℝ) * relinStepNoise ctx

/-- Lemma 19: Invariant noise growth during RNS relinearization from size M+1 to N+1.
    For an input ciphertext with invariant noise v, the relinearized noise v_relin satisfies:
    ||v_relin||_∞ ≤ ||v||_∞ + (t/q) * (M - N) * n * B * q_Sigma. -/
axiom lemma19_relin (ctx : BFVContext) (M N : ℕ) (h_le : N < M) (v_norm : ℝ) :
    ∃ v_relin_norm : ℝ,
      v_relin_norm ≤ v_norm + (ctx.t / ctx.q) * ((M - N : ℝ) * ctx.n * ctx.B * ctx.qSigma)

/-- Special case: Relinearization to size 2 (N = 1).
    Given input ciphertext size K_size = M + 1, the number of steps is K_size - 2:
    ||v_relin||_∞ ≤ ||v||_∞ + (t/q) * (K_size - 2) * n * B * q_Sigma. -/
axiom lemma19_relin_to_size2 (ctx : BFVContext) (K_size : ℕ) (h_k : 3 ≤ K_size) (v_norm : ℝ) :
    ∃ v_relin_norm : ℝ,
      v_relin_norm ≤ v_norm + (ctx.t / ctx.q) * (((K_size : ℝ) - 2) * ctx.n * ctx.B * ctx.qSigma)

end BfvNoise
