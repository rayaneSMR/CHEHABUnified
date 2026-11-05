-- BfvNoise.lean
-- Root module for the Lean 4 formalization of BFV Invariant Noise Bounds.

import BfvNoise.Basic
import BfvNoise.Norms
import BfvNoise.Lemmas.KeySwitch
import BfvNoise.Lemmas.Relin
import BfvNoise.Lemmas.Rotate
import BfvNoise.Lemmas.ModSwitch
import BfvNoise.Expression.Syntax
import BfvNoise.Expression.Bound
import BfvNoise.Expression.Soundness
import BfvNoise.Expression.Budget
import BfvNoise.CppAlignment
