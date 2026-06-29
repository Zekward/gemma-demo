-- bondsec: machine-verified bond facts. Plain Lean 4; each `by decide` that compiles IS the proof.
structure Bond where
  couponBp     : Nat   -- coupon in basis points (5.350% = 535)
  maturityYear : Nat
  principalMM  : Nat   -- principal, $ millions
  senior       : Bool
  deriving Repr


-- ## SPCX-2031
def SPCX_2031 : Bond := { couponBp := 535, maturityYear := 2031, principalMM := 7000, senior := true }
theorem SPCX_2031_f0 : SPCX_2031.couponBp = 535 := by decide   -- coupon = 5.350%
theorem SPCX_2031_f1 : SPCX_2031.maturityYear > 2026 := by decide   -- matures (2031) after issue (2026)
theorem SPCX_2031_f2 : SPCX_2031.principalMM > 0 := by decide   -- principal 7000MM > 0
theorem SPCX_2031_f3 : SPCX_2031.senior = true := by decide   -- ranks senior

-- ## SPCX-2033
def SPCX_2033 : Bond := { couponBp := 565, maturityYear := 2033, principalMM := 6000, senior := true }
theorem SPCX_2033_f0 : SPCX_2033.couponBp = 565 := by decide   -- coupon = 5.650%
theorem SPCX_2033_f1 : SPCX_2033.maturityYear > 2026 := by decide   -- matures (2033) after issue (2026)
theorem SPCX_2033_f2 : SPCX_2033.principalMM > 0 := by decide   -- principal 6000MM > 0
theorem SPCX_2033_f3 : SPCX_2033.senior = true := by decide   -- ranks senior

-- ## SPCX-2036
def SPCX_2036 : Bond := { couponBp := 588, maturityYear := 2036, principalMM := 6000, senior := true }
theorem SPCX_2036_f0 : SPCX_2036.couponBp = 588 := by decide   -- coupon = 5.880%
theorem SPCX_2036_f1 : SPCX_2036.maturityYear > 2026 := by decide   -- matures (2036) after issue (2026)
theorem SPCX_2036_f2 : SPCX_2036.principalMM > 0 := by decide   -- principal 6000MM > 0
theorem SPCX_2036_f3 : SPCX_2036.senior = true := by decide   -- ranks senior

-- ## SPCX-2046
def SPCX_2046 : Bond := { couponBp := 660, maturityYear := 2046, principalMM := 2500, senior := true }
theorem SPCX_2046_f0 : SPCX_2046.couponBp = 660 := by decide   -- coupon = 6.600%
theorem SPCX_2046_f1 : SPCX_2046.maturityYear > 2026 := by decide   -- matures (2046) after issue (2026)
theorem SPCX_2046_f2 : SPCX_2046.principalMM > 0 := by decide   -- principal 2500MM > 0
theorem SPCX_2046_f3 : SPCX_2046.senior = true := by decide   -- ranks senior

-- ## SPCX-2056
def SPCX_2056 : Bond := { couponBp := 665, maturityYear := 2056, principalMM := 3500, senior := true }
theorem SPCX_2056_f0 : SPCX_2056.couponBp = 665 := by decide   -- coupon = 6.650%
theorem SPCX_2056_f1 : SPCX_2056.maturityYear > 2026 := by decide   -- matures (2056) after issue (2026)
theorem SPCX_2056_f2 : SPCX_2056.principalMM > 0 := by decide   -- principal 3500MM > 0
theorem SPCX_2056_f3 : SPCX_2056.senior = true := by decide   -- ranks senior

-- ## edge SPCX-2031 -> SPCX-2033 (SIBLING_TRANCHE)
example : SPCX_2031.couponBp < SPCX_2033.couponBp := by decide   -- coupon ladder
example : SPCX_2031.maturityYear < SPCX_2033.maturityYear := by decide   -- maturity ordering
example : (SPCX_2031.senior = SPCX_2033.senior) = true := by decide   -- seniority match

-- ## edge SPCX-2033 -> SPCX-2036 (SIBLING_TRANCHE)
example : SPCX_2033.couponBp < SPCX_2036.couponBp := by decide   -- coupon ladder
example : SPCX_2033.maturityYear < SPCX_2036.maturityYear := by decide   -- maturity ordering
example : (SPCX_2033.senior = SPCX_2036.senior) = true := by decide   -- seniority match

-- ## edge SPCX-2036 -> SPCX-2046 (SIBLING_TRANCHE)
example : SPCX_2036.couponBp < SPCX_2046.couponBp := by decide   -- coupon ladder
example : SPCX_2036.maturityYear < SPCX_2046.maturityYear := by decide   -- maturity ordering
example : (SPCX_2036.senior = SPCX_2046.senior) = true := by decide   -- seniority match

-- ## edge SPCX-2046 -> SPCX-2056 (SIBLING_TRANCHE)
example : SPCX_2046.couponBp < SPCX_2056.couponBp := by decide   -- coupon ladder
example : SPCX_2046.maturityYear < SPCX_2056.maturityYear := by decide   -- maturity ordering
example : (SPCX_2046.senior = SPCX_2056.senior) = true := by decide   -- seniority match
