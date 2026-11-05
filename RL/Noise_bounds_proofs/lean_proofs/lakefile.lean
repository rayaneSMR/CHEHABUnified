import Lake
open Lake DSL

package "bfv_noise" where
  leanOptions := #[⟨`autoImplicit, false⟩]

@[default_target]
lean_lib «BfvNoise» where
  -- Library configuration
