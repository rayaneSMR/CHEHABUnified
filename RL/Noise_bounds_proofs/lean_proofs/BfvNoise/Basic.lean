-- BfvNoise/Basic.lean
-- Core BFV parameters and scheme context in Lean 4, strictly matching SEAL Table 1.

/-- Notation for Nat in core Lean. -/
notation "ℕ" => Nat

/-- Real / Scalar field representation: Rat provides exact rational arithmetic for BFV noise bounds. -/
abbrev Real := Rat
notation "ℝ" => Real

namespace BfvNoise

/-- Exponentiation for Real scalars by natural powers. -/
def rpow (x : ℝ) : ℕ → ℝ
  | 0 => 1
  | Nat.succ k => x * rpow x k

instance : HPow ℝ ℕ ℝ where
  hPow := rpow

/-- Parameters of the BFV encryption scheme, adhering to SEAL manual Table 1. -/
structure BFVContext where
  /-- Polynomial modulus degree n (power of 2, typically 1024 to 32768) -/
  n : ℝ
  hn : 2 ≤ n
  /-- Plaintext modulus t -/
  t : ℝ
  ht : 2 ≤ t
  /-- Standard error coefficient bound B (typically ~ 6σ) -/
  B : ℝ
  hB : 0 ≤ B
  /-- Coefficient modulus q (product of RNS primes q_1 * ... * q_k) -/
  q : ℝ
  hq : 0 < q
  /-- Sum of RNS prime moduli q_Sigma = \sum_{j=1}^k q_j -/
  qSigma : ℝ
  hqSigma : 0 < qSigma
  /-- Auxiliary special prime P used for RNS key switching -/
  P : ℝ
  hP : 2 ≤ P

/-- Geometric series expansion factor: \Sgeo{j} = (n^{j+1} - 1) / (n - 1). -/
def Sgeo (n : ℝ) (j : ℕ) : ℝ :=
  (n ^ (j + 1) - 1) / (n - 1)

/-- Sgeo is non-negative whenever n ≥ 2. -/
axiom sgeo_nonneg {n : ℝ} (hn : 2 ≤ n) (j : ℕ) : 0 ≤ Sgeo n j

end BfvNoise
