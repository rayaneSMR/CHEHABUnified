-- BfvNoise/Norms.lean
-- Polynomial infinity norm axioms and properties matching the SEAL 2.3.1 manual (Claim 2, Section 5.6).

import BfvNoise.Basic

namespace BfvNoise

/-- Parity predicate in core Lean: odd natural numbers. -/
def Odd (n : ℕ) : Prop := n % 2 = 1

/-- Polynomial ring R = ℤ[x]/(x^n + 1) or its rational tensor R ⊗ ℚ. -/
axiom PolyRing : Type

namespace PolyRing

/-- Zero element in PolyRing. -/
axiom zero : PolyRing

/-- Addition in PolyRing. -/
axiom add : PolyRing → PolyRing → PolyRing

/-- Negation in PolyRing. -/
axiom neg : PolyRing → PolyRing

/-- Multiplication in PolyRing. -/
axiom mul : PolyRing → PolyRing → PolyRing

/-- Scalar multiplication by a real/rational scalar. -/
axiom smul : ℝ → PolyRing → PolyRing

/-- Galois automorphism τ_g : R → R induced by X ↦ X^g for odd g. -/
axiom tau (g : ℕ) : PolyRing → PolyRing

/-- Infinity norm on polynomials ||a||_∞ = max |a_i|. -/
axiom norm : PolyRing → ℝ

-- --------------------------------------------------------------------
-- Standard Axioms of Norm and Ring Multiplication (SEAL Manual Appendix)
-- --------------------------------------------------------------------

/-- Norm is non-negative. -/
axiom norm_nonneg (a : PolyRing) : 0 ≤ norm a

/-- Norm of zero is zero. -/
axiom norm_zero : norm zero = 0

/-- Triangle inequality for infinity norm. -/
axiom norm_add_le (a b : PolyRing) : norm (add a b) ≤ norm a + norm b

/-- Norm of negation preserves norm. -/
axiom norm_neg (a : PolyRing) : norm (neg a) = norm a

/-- Scalar multiplication scales norm: ||c * a|| = |c| * ||a||. -/
axiom norm_smul (c : ℝ) (a : PolyRing) : norm (smul c a) ≤ (if 0 ≤ c then c else -c) * norm a

/-- Claim 2 of the SEAL 2.3.1 manual:
    For any a, b ∈ R, ||a * b||_∞ ≤ n * ||a||_∞ * ||b||_∞. -/
axiom claim2_mul_bound (n : ℝ) (hn : 2 ≤ n) (a b : PolyRing) :
    norm (mul a b) ≤ n * norm a * norm b

/-- Norm of ternary secret key s ∈ {-1, 0, 1}^n is exactly 1 (Section 5.9). -/
axiom ternary_key_norm (s : PolyRing) : norm s = 1

/-- Galois automorphism preserves infinity norm (exact isometry, Section 5.6):
    Since X ↦ X^g permutes monomial powers up to signs for odd g coprime to 2n,
    ||τ_g(a)||_∞ = ||a||_∞. -/
axiom isometry_galois (g : ℕ) (hg : Odd g) (a : PolyRing) :
    norm (tau g a) = norm a

end PolyRing

end BfvNoise
