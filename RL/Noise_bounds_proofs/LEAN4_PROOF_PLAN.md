# Lean 4 Implementation Plan: BFV Invariant Noise Bounds

This document provides a modular, step-by-step implementation plan for an LLM agent to formalize and verify in **Lean 4** (with `Mathlib4`):
1. **The Derived Lemmas (Track 1 & Track 2)**: Key Switching (Lemma 18), Relinearization (Lemma 19), Galois Rotation (Lemma 20), and Modulus Switching (Lemma 21).
2. **The General FHE Expression Bound (Track 3)**: Structural induction proof of soundness for an arbitrary expression $\mathcal{E}$ of size $N$ (Lemma 22), plus Decryption Correctness and Noise Budget guarantees.
3. **Soundness of C++ Estimator**: Formal proof that the conservative simplifications in `bfv_noise_bound.cpp` upper-bound the mathematical invariants.

---

## Architecture Overview

```
BfvNoise/
├── Basic.lean          -- SEAL parameters, polynomial ring R, invariant noise definition
├── Norms.lean          -- Polynomial infinity norm, Claim 2 (submultiplicativity), isometry of tau_g
├── Lemmas/
│   ├── KeySwitch.lean  -- Lemma 18 (RNS key switching with special prime P)
│   ├── Relin.lean      -- Lemma 19 (Iterated relinearization to size 2, top-component invariance)
│   ├── Rotate.lean     -- Lemma 20 (Galois automorphism and slot rotation)
│   └── ModSwitch.lean  -- Lemma 21 (Modulus switching and geometric series sum)
├── Expression/
│   ├── Syntax.lean     -- Inductive AST (BFVExpr), size, and modulus tracking
│   ├── Bound.lean      -- Recursive noise bound function B(E)
│   ├── Soundness.lean  -- Lemma 22 (Proof of exactNoise E ≤ B(E) by structural induction)
│   └── Budget.lean     -- Decryption correctness (B < 1/2) and noise budget lower bound
└── CppAlignment.lean   -- Proof that bfv_noise_bound.cpp is a conservative upper bound
```

---

## Step 0: Environment & Lakefile Setup

* **Target Toolchain**: Lean `v4.8.0` (or latest stable) + `Mathlib4`.
* **Action**: Create `lakefile.lean` and `lean-toolchain`.

```lean
-- lakefile.lean
import Lake
open Lake DSL

package "bfv_noise" where
  leanOptions := #[⟨`autoImplicit, false⟩]

require mathlib from git "https://github.com/leanprover-community/mathlib4.git"

@[default_target]
lean_lib "BfvNoise" where
```

---

## Step 1: Core Algebra & Norms (`Basic.lean`, `Norms.lean`)

### Task 1.1: Scheme Parameters & Context (`Basic.lean`)
Define a structure bundling SEAL context parameters matching Table 1:
```lean
structure BFVContext where
  n      : ℕ           -- poly_modulus_degree (power of 2)
  hn     : 2 ≤ n
  t      : ℕ           -- plain_modulus
  ht     : 2 ≤ t
  B      : ℝ           -- noise_max_deviation
  hB     : 0 ≤ B
  q      : ℝ           -- coeff_modulus product
  hq     : 0 < q
  qSigma : ℝ           -- sum of RNS primes
  hqSigma: 0 < qSigma
  P      : ℝ           -- special prime
  hP     : 2 ≤ P
```

### Task 1.2: Ring & Norm Definitions (`Norms.lean`)
* **Ring $R$**: Represent elements as polynomials over $\mathbb{Z}$ (or $\mathbb{Q}$) with degree $< n$.
* **Infinity Norm**: Define $\norm{a}_\infty = \max_{0 \le i < n} |a_i|$.
* **Theorems to Prove**:
  1. `claim2_mul_bound (a b : R) : norm (a * b) ≤ (n : ℝ) * norm a * norm b`
  2. `isometry_galois (g : ℕ) (hg : Odd g) (a : R) : norm (tau g a) = norm a`
  3. `ternary_key_norm (s : R) (hs : s ∈ Ternary) : norm s = 1`

* **Tactics to Use**: `positivity`, `norm_num`, `fin_cases`, `omega`.

---

## Step 2: Formalize Single-Step Extension Lemmas (`Lemmas/`)

### Task 2.1: Key Switching (`KeySwitch.lean` - Lemma 18)
* **Goal**: Prove $d_0 + d_1 s = c s' + E + q r$ with $\norm{E} \le \frac{n B q_\Sigma}{P} + \frac{n+1}{2} \le n B q_\Sigma$.
* **Steps**:
  1. Define RNS key-switching key: $b_j + a_j s = -e_j + P \gamma_j s' + q P r_j$.
  2. Define rounding: $d_i = \lfloor x_i / P \rceil + q k_i = x_i / P + \delta_i + q k_i$ with $\norm{\delta_i} \le 1/2$.
  3. Prove CRT identity: $\sum_{j=1}^k c^{(j)} \gamma_j = c + q K_{\mathrm{crt}}$.
  4. Prove algebraic equality using `ring` / `linear_combination`.
  5. Prove norm bound on $E = -\frac{1}{P}\sum c^{(j)} e_j + \delta_0 + \delta_1 s$ via triangle inequality and `claim2_mul_bound`.

### Task 2.2: Relinearization (`Relin.lean` - Lemma 19)
* **Goal**: Prove $\norm{\vrelin} \le \norm{v} + \frac{t}{q}(K_{\mathrm{size}}-2) n B q_\Sigma$.
* **Steps**:
  1. Define 1-step relinearization reducing size $K+1 \to K$ by key-switching $c_K$.
  2. **Top-Component Invariance Lemma**: Prove that for any step $K$, components with index $i \ge 2$ are untouched by previous steps $M, \dots, K+1$.
  3. Prove intermediate lift: $[c_i + d_i]_q = c_i + d_i + q A_i$, absorbing $q(A_0 + A_1 s)$ into the integer multiple $t r'$.
  4. Prove multi-step bound by finite sum accumulation over $M-N$ steps.

### Task 2.3: Galois Rotation (`Rotate.lean` - Lemma 20)
* **Goal**: Prove $\norm{\vrot} \le \norm{v} + \frac{t}{q} n B q_\Sigma$.
* **Steps**:
  1. Apply $\tau_g$ to $\frac{t}{q}(c_0 + c_1 s) = m + v + at$.
  2. Use `isometry_galois` to obtain $\norm{\tau_g(v)} = \norm{v}$.
  3. Substitute Lemma 18 on $(d_0, d_1) = \KS(\tau_g(c_1))$ and absorb modular reductions in $R_q$.

### Task 2.4: Modulus Switching (`ModSwitch.lean` - Lemma 21)
* **Goal**: Prove $\norm{\vms} \le \norm{v} + \frac{t}{2q'} \frac{n^{j+1}-1}{n-1}$.
* **Steps**:
  1. Define centered reduction error: $\varepsilon_i = -[c_i]_{q_k}/q_k$, with $\norm{\varepsilon_i} \le 1/2$.
  2. Prove inductive bound: $\norm{s^i} \le n^{i-1} \implies \norm{\varepsilon_i s^i} \le \frac{1}{2} n^i$.
  3. Apply geometric progression sum identity: `Mathlib.geom_sum_mul_add`.

---

## Step 3: Expression AST & Evaluator (`Expression/`)

### Task 3.1: Syntax AST (`Syntax.lean`)
Define the inductive datatype representing any valid FHE program of size $N$:
```lean
inductive BFVExpr where
  | fresh          (m_norm : ℝ) (hm : 0 ≤ m_norm)
  | negate         (e : BFVExpr)
  | add            (e1 e2 : BFVExpr)
  | sub            (e1 e2 : BFVExpr)
  | add_plain      (e : BFVExpr) (m2_norm : ℝ) (hm : 0 ≤ m2_norm)
  | sub_plain      (e : BFVExpr) (m2_norm : ℝ) (hm : 0 ≤ m2_norm)
  | mul_plain      (e : BFVExpr) (m2_l1 : ℝ)   (hm : 0 ≤ m2_l1)
  | mul            (e1 e2 : BFVExpr)
  | relin          (e : BFVExpr)
  | rotate         (e : BFVExpr)
  | mod_switch     (e : BFVExpr)
```

Define expression size ($N = \text{number of nodes}$):
```lean
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
```

### Task 3.2: Recursive Noise Bound Function (`Bound.lean`)
Implement $\mathcal{B}(\mathcal{E})$ exactly matching Table 2 of `extensions.tex`:
* Constant bounds for unknown messages: $\norm{m_i} \le \lfloor t/2 \rfloor$, $N_{m_i} \le n$.
* Include plain addition/subtraction remainder: $+\frac{r_t(q)}{q}\norm{m_2}$.
* Multiplication bilinear formula with geometric coefficients.

---

## Step 4: Inductive Soundness Theorem (`Soundness.lean`)

### Task 4.1: General Soundness Theorem (Lemma 22)
Formulate and automate the main theorem:
```lean
theorem bfv_expression_soundness (ctx : BFVContext) (e : BFVExpr) :
    exactNoise ctx e ≤ noiseBound ctx e := by
  induction e with
  | fresh m hm =>
      exact lemma9_fresh ctx m hm
  | negate e ih =>
      rw [noise_negate, noiseBound]
      exact ih
  | add e1 e2 ih1 ih2 =>
      have h := lemma10_add ctx e1 e2
      dsimp [noiseBound]; linarith
  | sub e1 e2 ih1 ih2 =>
      have h := lemma16_sub ctx e1 e2
      dsimp [noiseBound]; linarith
  | add_plain e m hm ih =>
      have h := lemma14_add_plain ctx e m hm
      dsimp [noiseBound]; linarith
  | sub_plain e m hm ih =>
      have h := lemma17_sub_plain ctx e m hm
      dsimp [noiseBound]; linarith
  | mul_plain e l1 hl1 ih =>
      have h := lemma13_mul_plain ctx e l1 hl1
      dsimp [noiseBound]; nlinarith
  | mul e1 e2 ih1 ih2 =>
      have h := lemma11_mul ctx e1 e2
      dsimp [noiseBound]
      -- Positivity of C1, C2, 3n preserves inequality under nlinarith
      have hpos : 0 ≤ 3 * ctx.n := by positivity
      nlinarith
  | relin e ih =>
      have h := lemma19_relin ctx e
      dsimp [noiseBound]; linarith
  | rotate e ih =>
      have h := lemma20_rotate ctx e
      dsimp [noiseBound]; linarith
  | mod_switch e ih =>
      have h := lemma21_modswitch ctx e
      dsimp [noiseBound]; linarith
```

---

## Step 5: Decryption Correctness & Noise Budget (`Budget.lean`)

* **Theorem 1 (Decryption Correctness)**:
  ```lean
  theorem decryption_correctness (ctx : BFVContext) (e : BFVExpr)
      (h : noiseBound ctx e < 1/2) :
      decrypt (evalCipher ctx e) = evalPlain ctx e
  ```
  *Proof*: Direct application of `exactNoise ctx e ≤ noiseBound ctx e < 1/2` and Lemma 1.

* **Theorem 2 (Noise Budget Lower Bound)**:
  ```lean
  theorem noise_budget_lower_bound (ctx : BFVContext) (e : BFVExpr)
      (h : noiseBound ctx e < 1/2) :
      noiseBudget ctx e ≥ -Real.logb 2 (2 * noiseBound ctx e)
  ```
  *Proof*: Monotonicity of $x \mapsto -\log_2(2x)$ via `Real.logb_le_logb`.

---

## Step 6: Alignment with C++ Implementation (`CppAlignment.lean`)

Prove that the software implementation in `bfv_noise_bound.cpp` is a conservative over-approximation of the proved mathematical bound $\mathcal{B}(\mathcal{E})$:
1. **Omission of $P$**: Prove $n B q_\Sigma / P + (n+1)/2 \le n B q_\Sigma$.
2. **Conservative Geometric Sum**: Prove $\Sgeo{j} \le n \Sgeo{j} = \sum_{i=1}^{j+1} n^i$.
3. **Directed Rounding**: Formalize that IEEE-754 upward rounding (`round_up` / `std::nextafter`) preserves the mathematical inequality $\mathcal{B}(\mathcal{E}) \le \mathcal{B}_{\mathrm{cpp}}(\mathcal{E})$.

---

## Execution Checklist for LLM Agents

| Step | Target File | Primary Lean Tactics | Acceptance Criterion |
| :--- | :--- | :--- | :--- |
| **0** | `lakefile.lean` | Shell / Lake | `lake build` succeeds with empty lib. |
| **1** | `Basic.lean`, `Norms.lean` | `positivity`, `norm_num` | `claim2_mul_bound` and `isometry_galois` proved. |
| **2.1** | `KeySwitch.lean` | `ring`, `linear_combination` | Lemma 18 proved with zero `sorry`. |
| **2.2** | `Relin.lean` | `linarith`, `omega` | Lemma 19 proved with top invariance. |
| **2.3** | `Rotate.lean` | `linarith`, `rw` | Lemma 20 proved using isometry. |
| **2.4** | `ModSwitch.lean` | `geom_sum_mul_add` | Lemma 21 proved for size $j+1$. |
| **3** | `Syntax.lean`, `Bound.lean` | Lean 4 Pattern Matching | AST and $\mathcal{B}(\mathcal{E})$ compile cleanly. |
| **4** | `Soundness.lean` | `induction`, `linarith`, `nlinarith` | Lemma 22 proved for all 11 operations. |
| **5** | `Budget.lean` | `linarith`, `Real.logb` monotonicity | Decryption correctness & budget bounds proved. |
| **6** | `CppAlignment.lean` | `nlinarith`, `norm_num` | Theorem: $\norm{v} \le \mathcal{B}(\mathcal{E}) \le \mathcal{B}_{\mathrm{cpp}}(\mathcal{E})$. |
