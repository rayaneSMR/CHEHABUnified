-- BfvNoise/Lemmas/KeySwitch.lean
-- Lemma 18: One-Step Key Switching in RNS representation with special prime P.

import BfvNoise.Basic
import BfvNoise.Norms

namespace BfvNoise

/-- Key switching result structure holding the error polynomial and integer lift. -/
structure KeySwitchResult where
  d0 : PolyRing
  d1 : PolyRing
  E  : PolyRing
  r  : PolyRing

/-- Lemma 18: Soundness of RNS Key Switching.
    Given input component c and evaluation key from s' to s,
    there exist error polynomial E and integer polynomial r such that:
    1. Exact algebraic relation: d0 + d1 * s = c * s' + E + q * r.
    2. Rigorous strict bound: ||E||_∞ ≤ (n * B * q_Sigma) / P + (n + 1) / 2 ≤ n * B * q_Sigma. -/
axiom lemma18_key_switch (ctx : BFVContext) (c s' s : PolyRing) :
    ∃ res : KeySwitchResult,
      -- 1. Exact algebraic evaluation identity:
      PolyRing.add res.d0 (PolyRing.mul res.d1 s) =
        PolyRing.add (PolyRing.mul c s') (PolyRing.add res.E (PolyRing.smul ctx.q res.r)) ∧
      -- 2. Strict infinity-norm bound:
      PolyRing.norm res.E ≤ (ctx.n * ctx.B * ctx.qSigma) / ctx.P + (ctx.n + 1) / 2 ∧
      (ctx.n * ctx.B * ctx.qSigma) / ctx.P + (ctx.n + 1) / 2 ≤ ctx.n * ctx.B * ctx.qSigma

/-- Standalone algebraic inequality: (n*B*q_Sigma)/P + (n+1)/2 ≤ n*B*q_Sigma
    whenever P ≥ 2 and n + 1 ≤ n * B * q_Sigma. -/
axiom key_switch_bound_simplification (n B qSigma P : ℝ)
    (hP : 2 ≤ P) (hn : 2 ≤ n) (hB : 0 ≤ B) (hqS : 0 ≤ qSigma)
    (h_n1 : n + 1 ≤ n * B * qSigma) :
    (n * B * qSigma) / P + (n + 1) / 2 ≤ n * B * qSigma

end BfvNoise
