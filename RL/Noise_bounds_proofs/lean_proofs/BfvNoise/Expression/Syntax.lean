-- BfvNoise/Expression/Syntax.lean
-- Inductive Abstract Syntax Tree (AST) for arbitrary BFV expressions of size N.

import BfvNoise.Basic

namespace BfvNoise

/-- Inductive AST representing an arbitrary BFV homomorphic computation. -/
inductive BFVExpr where
  | fresh          (m_norm : ℝ) (hm : 0 ≤ m_norm)
  | negate         (e : BFVExpr)
  | add            (e1 e2 : BFVExpr)
  | sub            (e1 e2 : BFVExpr)
  | add_plain      (e : BFVExpr) (m2_norm : ℝ) (hm2 : 0 ≤ m2_norm)
  | sub_plain      (e : BFVExpr) (m2_norm : ℝ) (hm2 : 0 ≤ m2_norm)
  | mul_plain      (e : BFVExpr) (m2_l1 : ℝ)   (hl1 : 0 ≤ m2_l1)
  | mul            (e1 e2 : BFVExpr)
  | relin          (e : BFVExpr)
  | rotate         (e : BFVExpr)
  | mod_switch     (e : BFVExpr)

/-- Size of the expression (number of operation nodes N). -/
def exprSize : BFVExpr → ℕ
  | .fresh _ _       => 1
  | .negate e        => exprSize e + 1
  | .add e1 e2       => exprSize e1 + exprSize e2 + 1
  | .sub e1 e2       => exprSize e1 + exprSize e2 + 1
  | .add_plain e _ _ => exprSize e + 1
  | .sub_plain e _ _ => exprSize e + 1
  | .mul_plain e _ _ => exprSize e + 1
  | .mul e1 e2       => exprSize e1 + exprSize e2 + 1
  | .relin e         => exprSize e + 1
  | .rotate e        => exprSize e + 1
  | .mod_switch e    => exprSize e + 1

/-- Ciphertext size (number of polynomial components, e.g. 2 for size-2 ciphertext). -/
def cipherSize : BFVExpr → ℕ
  | .fresh _ _       => 2
  | .negate e        => cipherSize e
  | .add e1 e2       => max (cipherSize e1) (cipherSize e2)
  | .sub e1 e2       => max (cipherSize e1) (cipherSize e2)
  | .add_plain e _ _ => cipherSize e
  | .sub_plain e _ _ => cipherSize e
  | .mul_plain e _ _ => cipherSize e
  | .mul e1 e2       => cipherSize e1 + cipherSize e2 - 1
  | .relin _         => 2
  | .rotate _        => 2
  | .mod_switch e    => cipherSize e

/-- Modulus level along the modulus chain (increased by modulus switching). -/
def modulusLevel : BFVExpr → ℕ
  | .fresh _ _       => 0
  | .negate e        => modulusLevel e
  | .add e1 _        => modulusLevel e1
  | .sub e1 _        => modulusLevel e1
  | .add_plain e _ _ => modulusLevel e
  | .sub_plain e _ _ => modulusLevel e
  | .mul_plain e _ _ => modulusLevel e
  | .mul e1 _        => modulusLevel e1
  | .relin e         => modulusLevel e
  | .rotate e        => modulusLevel e
  | .mod_switch e    => modulusLevel e + 1

/-- Every valid expression has size at least 1. -/
theorem exprSize_pos (e : BFVExpr) : 1 ≤ exprSize e := by
  induction e <;> (dsimp [exprSize]; omega)

/-- Every valid ciphertext has at least 2 components. -/
theorem cipherSize_ge_two (e : BFVExpr) : 2 ≤ cipherSize e := by
  induction e with
  | fresh _ _ => dsimp [cipherSize]; omega
  | negate e ih => dsimp [cipherSize]; exact ih
  | add e1 e2 ih1 ih2 => dsimp [cipherSize]; omega
  | sub e1 e2 ih1 ih2 => dsimp [cipherSize]; omega
  | add_plain e _ _ ih => dsimp [cipherSize]; exact ih
  | sub_plain e _ _ ih => dsimp [cipherSize]; exact ih
  | mul_plain e _ _ ih => dsimp [cipherSize]; exact ih
  | mul e1 e2 ih1 ih2 => dsimp [cipherSize]; omega
  | relin _ => dsimp [cipherSize]; omega
  | rotate _ => dsimp [cipherSize]; omega
  | mod_switch e ih => dsimp [cipherSize]; exact ih

end BfvNoise
