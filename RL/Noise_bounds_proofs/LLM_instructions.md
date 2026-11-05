# BFV Noise-Bound Extensions for Microsoft SEAL

## 1. Project context

The objective is to extend the noise-bound analysis provided in the Microsoft SEAL manual for BFV, while preserving SEAL's mathematical notation and proof style.

The work is divided into three tracks:

1. **RNS adaptations:** Adapt existing SEAL noise-bound lemmas to the RNS representation (only those who need to be adapted, i gues it is only for the key switching RNS not all the existing), where the coefficient modulus \(Q\) is decomposed into pairwise-coprime moduli \(q_i\). Focus on operations for which SEAL does not explicitly provide the corresponding RNS bound.
2. **Missing operation bounds:** Derive rigorous noise bounds for two operations for which SEAL does not provide a bound lemma.
3. **General expression bound:** Derive and prove a general noise bound for an arbitrary BFV expression of length \(n\), composed of combinations of the considered operations.

The current task concerns **Track 1 only**. Do not attempt Tracks 2 or 3.

## 2. Provided package

The package contains:

- **SEAL_manual_appendix.tex:** Original noise-bound definitions, lemmas, and their proofs
- **Notations.tex:  The mathematical notation and relevant derivations used in this project.
- **noise_bound_implementation:** My current implementation of `noise_bound`, provided as a reference for understanding the intended calculations. It is not an authoritative mathematical proof. : 
- **sealmanual-2-3-1.md** : The complete SEAL manual in case you need other things not available in the appendix.


Read the provided files before deriving anything. Identify the relevant definitions, assumptions, and operations. If a required definition or source is missing, explicitly report it rather than inventing one.

## 3. Task — Track 1: Adapt existing operations to RNS

Identify the operations for which SEAL provides a noise-bound lemma but does not explicitly provide the corresponding RNS-case bound.

For each such operation:

1. **State the adapted bound.** Derive the RNS noise-bound formula under clearly stated assumptions.
2. **Provide a formal proof.** Follow the mathematical style, structure, and level of rigor used in the SEAL manual. Show the intermediate steps and justify every nontrivial inequality or transformation.
3. **Explain the differences from SEAL.** Briefly identify what changes in the RNS case, why the adaptation is necessary, and whether additional assumptions or terms are introduced.
4. **Perform a correctness check.** At the end of each operation, include a dedicated correctness-check section. Verify:
   - Consistency with the definitions and assumptions in the SEAL manual.
   - Correct handling of the RNS moduli \(q_i\) and their relationship to \(Q\).
   - Validity of each inequality and mathematical transformation.
   - Whether the result reduces to the original SEAL bound under the appropriate non-RNS or equivalent assumptions.
   - Whether the derived bound is deterministic or relies on additional assumptions.

   Explicitly state any unresolved issue. Do not claim correctness if a step has not been justified.

## 4. Strict requirements

- **Notation:** Strictly preserve SEAL's original notation, symbols, variable names, subscripts, superscripts, and definitions. Do not rename, simplify, or redefine notation.
- **Proof style:** Follow SEAL's proof style as closely as possible. Use formal mathematical reasoning, not informal explanations or intuitive arguments.
- **Rigor:** Do not skip intermediate steps or silently introduce assumptions. Clearly distinguish established results from additional assumptions.
- **Source fidelity:** Do not modify or reinterpret SEAL's original results. Clearly distinguish the original lemma from its RNS adaptation.
- **Implementation:** Use my `noise_bound` implementation only as a reference. Do not assume that its formulas are mathematically correct.
- **Uncertainty:** If the available material is insufficient to establish a rigorous bound, explain precisely what is missing instead of guessing.

## 5. Output

Return a single LaTeX file named **`extensions.tex`**.

For each adapted operation, use the following structure:

1. Operation name and relevant SEAL lemma/reference.
2. Adapted RNS noise-bound statement.
3. Complete formal proof.
4. Remarks on differences from the original SEAL result.
5. Correctness check, including any unresolved issues.

The file must be self-contained enough to compile with the provided notation/macros, and must preserve the original notation throughout.
After each formulas derived and proven,fill the extension.tex, don't wait until the end.