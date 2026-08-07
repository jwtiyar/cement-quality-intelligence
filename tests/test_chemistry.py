"""Tests for chemistry.py — moduli, Bogue phases, liquid content, diagnostics.

Reference values verified against FLSmidth literature / ASTM C150
(the same numbers used in verify_cement_logic.py).
"""

import pytest

from chemistry import (
    BoguePhases,
    OxideAnalysis,
    analyze_clinker,
    calc_bogue,
    calc_liquid_content,
    calc_moduli,
    clinker_lsf_percent,
    lsf_advice,
    rawmix_diagnostics,
)


# --- Known-good reference case (FLS textbook values) -------------------------

REF_OXIDE = OxideAnalysis(SiO2=19.18, Al2O3=4.96, Fe2O3=3.90, CaO=62.51, SO3=2.26)


class TestModuli:
    # Tolerance matches verify_cement_logic.py (diff < 0.002). The FLS reference
    # value for LSF is approximate; the verified script accepts 0.0016 diff.
    TOL = 0.002

    def test_known_fls_values(self):
        mod = calc_moduli(REF_OXIDE)
        assert mod.LSF == pytest.approx(0.9797, abs=self.TOL)
        assert mod.SM == pytest.approx(2.1648, abs=1e-4)
        assert mod.AM == pytest.approx(1.2718, abs=1e-4)

    def test_lsf_percent_property(self):
        mod = calc_moduli(REF_OXIDE)
        assert mod.LSF_percent == pytest.approx(97.97, abs=self.TOL * 100)

    def test_zero_denominator_safe(self):
        # All zeros must not raise (return 0.0)
        mod = calc_moduli(OxideAnalysis())
        assert mod.LSF == 0.0
        assert mod.SM == 0.0
        assert mod.AM == 0.0

    def test_am_infinite_guarded(self):
        # Fe2O3 = 0 → AM must be 0.0, not ZeroDivisionError
        ox = OxideAnalysis(SiO2=20, Al2O3=5, Fe2O3=0, CaO=63)
        mod = calc_moduli(ox)
        assert mod.AM == 0.0
        assert mod.SM == pytest.approx(4.0)  # 20 / 5


class TestBogue:
    def test_known_fls_values(self):
        phases = calc_bogue(REF_OXIDE)
        assert phases.C3S == pytest.approx(63.3664, abs=1e-3)
        assert phases.C2S == pytest.approx(7.1854, abs=1e-3)
        assert phases.C3A == pytest.approx(6.5452, abs=1e-3)
        assert phases.C4AF == pytest.approx(11.8677, abs=1e-3)

    def test_extreme_chemistry_reported_not_clamped(self):
        # Extreme chemistry must NOT be silently clamped to 0 — the raw negative
        # value is the signal that the composition is physically impossible.
        phases = calc_bogue(OxideAnalysis(SiO2=40, Al2O3=10, Fe2O3=5, CaO=10))
        assert phases.C3S < 0

    def test_phase_sum_reasonable(self):
        # C3S+C2S+C3A+C4AF should be near 100 for a normal clinker
        phases = calc_bogue(REF_OXIDE)
        assert 85 <= (phases.C3S + phases.C2S + phases.C3A + phases.C4AF) <= 100


class TestLiquidContent:
    def test_lea_parker_reference(self):
        # ASTM/Lea&Parker at 1400C: 1.13*C3A + 1.35*C4AF + MgO + Na2O + 0.65*K2O
        ox = OxideAnalysis(MgO=2.0, Na2O=0.2, K2O=0.6)
        phases = calc_bogue(REF_OXIDE)
        lc = calc_liquid_content(phases, ox)
        expected = 1.13 * 6.5452 + 1.35 * 11.8677 + 2.0 + 0.2 + 0.65 * 0.6
        assert lc == pytest.approx(expected, abs=1e-6)

    def test_without_oxides_defaults_to_zero(self):
        phases = calc_bogue(REF_OXIDE)
        lc = calc_liquid_content(phases)
        assert lc > 20  # still a meaningful number from C3A/C4AF alone


class TestClinkerLSF:
    def test_matches_calc_moduli_path(self):
        # clinker_lsf_percent must agree with the moduli path
        ox = REF_OXIDE
        mod = calc_moduli(ox)
        direct = clinker_lsf_percent(ox.CaO, ox.SiO2, ox.Al2O3, ox.Fe2O3, ox.SO3)
        assert direct == pytest.approx(mod.LSF_percent, abs=1e-3)

    def test_zero_denominator(self):
        assert clinker_lsf_percent(0, 0, 0, 0, 0) == 0.0


class TestAnalyzeClinker:
    def test_shape_and_rounding(self):
        result = analyze_clinker(REF_OXIDE)
        assert set(result["moduli"]) == {"LSF", "SM", "AM"}
        assert set(result["phases"]) == {"C3S", "C2S", "C3A", "C4AF"}
        assert "liquid_content" in result
        # rounded to 2 decimals; tolerance matches verify script (0.002 ratio)
        assert result["moduli"]["LSF"] == pytest.approx(97.97, abs=0.2)

    def test_valid_chemistry_flags(self):
        result = analyze_clinker(REF_OXIDE)
        assert result["phases_valid"] is True
        assert result["negative_phases"] == []

    def test_invalid_chemistry_flagged(self):
        result = analyze_clinker(OxideAnalysis(SiO2=40, Al2O3=10, Fe2O3=5, CaO=10))
        assert result["phases_valid"] is False
        assert result["negative_phases"]  # non-empty list of phase names


class TestLsfAdvice:
    def test_low(self):
        assert "increase" in lsf_advice(90.0).lower()

    def test_optimal(self):
        assert "optimal" in lsf_advice(95.0).lower()

    def test_high(self):
        msg = lsf_advice(99.0)
        assert "Do NOT increase CaO" in msg


class TestRawmixDiagnostics:
    def test_src_c3a_failure(self):
        # SRC with C3A > 5 must emit an error (ASTM C150 Type V limit)
        diags = rawmix_diagnostics("SRC", 92.0, 2.5, 0.9, c3a=6.2, liquid_content=25.0)
        errors = [d for d in diags if d["severity"] == "error"]
        assert len(errors) == 1
        assert "Compliance Failure" in errors[0]["message"]

    def test_src_high_am_warning(self):
        diags = rawmix_diagnostics("SRC", 92.0, 2.5, am=1.4, c3a=3.0, liquid_content=25.0)
        assert any("Alumina Modulus" in d["message"] for d in diags)

    def test_opc_hard_burning_risk(self):
        diags = rawmix_diagnostics("OPC", 98.5, 2.5, 1.5, c3a=8.0, liquid_content=25.0)
        assert any("Hard-Burning" in d["message"] for d in diags)

    def test_low_liquid_warning(self):
        diags = rawmix_diagnostics("OPC", 95.0, 2.5, 1.5, c3a=6.0, liquid_content=18.0)
        assert any("Liquid" in d["message"] for d in diags)

    def test_healthy_mix_no_warnings(self):
        diags = rawmix_diagnostics("OPC", 95.0, 2.4, 1.5, c3a=7.0, liquid_content=26.0)
        assert diags == []
