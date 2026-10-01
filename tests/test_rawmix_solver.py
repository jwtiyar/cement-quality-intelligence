"""Tests for rawmix_solver.py — FLS 4x4 raw-mix proportion solver."""

import pytest

from rawmix_solver import MaterialComp, calculate_rawmix, _clinker_basis, _fuel_so3

# A chemically-plausible OPC raw-mix (realistic limestone / clay / sand / iron ore)
BASE_MATERIALS = {
    "limestone": {
        "SiO2": 3.0, "Al2O3": 0.8, "Fe2O3": 0.5, "CaO": 52.0,
        "MgO": 0.5, "Na2O": 0.05, "K2O": 0.1, "SO3": 0.1,
        "LOI": 42.0, "H2O": 2.0,
    },
    "shale": {
        "SiO2": 60.0, "Al2O3": 16.0, "Fe2O3": 7.0, "CaO": 3.0,
        "MgO": 2.0, "Na2O": 0.3, "K2O": 2.0, "SO3": 0.5,
        "LOI": 5.0, "H2O": 8.0,
    },
    "sand": {
        "SiO2": 92.0, "Al2O3": 3.0, "Fe2O3": 1.5, "CaO": 0.5,
        "MgO": 0.1, "Na2O": 0.1, "K2O": 0.3, "SO3": 0.0,
        "LOI": 1.0, "H2O": 1.0,
    },
    "pyrite": {
        "SiO2": 8.0, "Al2O3": 2.0, "Fe2O3": 75.0, "CaO": 1.0,
        "MgO": 0.5, "Na2O": 0.1, "K2O": 0.2, "SO3": 0.3,
        "LOI": 10.0, "H2O": 3.0,
    },
}

HFO = {"heat": 730, "calorific": 9800, "sulfur": 2.5}


def solve_payload(targets=None, cement_type="OPC"):
    return {
        "mode": "solve",
        "cement_type": cement_type,
        "materials": BASE_MATERIALS,
        "hfo": HFO,
        "targets": targets or {"LSF": 95.0, "SM": 2.4, "AM": 1.5},
    }


class TestFuelSO3:
    def test_formula(self):
        # SO3_from_fuel = (heat/cal) * sulfur * 2.25
        assert _fuel_so3(730, 9800, 2.5) == pytest.approx((730 / 9800) * 2.5 * 2.25)

    def test_zero_sulfur(self):
        assert _fuel_so3(730, 9800, 0.0) == 0.0


class TestClinkerBasis:
    def test_loi_correction(self):
        basis = _clinker_basis(
            {"limestone": MaterialComp(**BASE_MATERIALS["limestone"])}
        )
        # CaO on clinker basis = 52.0 / (1 - 0.42) = 89.66
        assert basis["limestone"]["CaO"] == pytest.approx(89.66, abs=0.01)

    def test_loi_100_rejected(self):
        bad = {"m": MaterialComp(SiO2=1, Al2O3=1, Fe2O3=1, CaO=1, LOI=100.0)}
        with pytest.raises(ValueError):
            _clinker_basis(bad)


class TestSolveMode:
    def test_hfo_sulfur_does_not_change_clinker_mix_targets(self):
        with_sulfur = solve_payload()
        without_sulfur = solve_payload()
        without_sulfur["hfo"] = {**HFO, "sulfur": 0.0}

        sulfur_result = calculate_rawmix(with_sulfur)
        no_sulfur_result = calculate_rawmix(without_sulfur)

        assert sulfur_result["dry_proportions"] == no_sulfur_result["dry_proportions"]
        assert sulfur_result["clinker"]["LSF"] == no_sulfur_result["clinker"]["LSF"]
        assert sulfur_result["clinker"]["SO3"] > no_sulfur_result["clinker"]["SO3"]

    def test_hits_targets(self):
        result = calculate_rawmix(solve_payload())
        cl = result["clinker"]
        assert cl["LSF"] == pytest.approx(95.0, abs=0.5)
        assert cl["SM"] == pytest.approx(2.4, abs=0.05)
        assert cl["AM"] == pytest.approx(1.5, abs=0.05)

    def test_proportions_sum_100(self):
        result = calculate_rawmix(solve_payload())
        total = sum(result["dry_proportions"].values())
        assert total == pytest.approx(100.0, abs=0.2)

    def test_all_proportions_positive(self):
        result = calculate_rawmix(solve_payload())
        assert all(v >= 0 for v in result["dry_proportions"].values())

    def test_limestone_dominant(self):
        result = calculate_rawmix(solve_payload())
        assert result["dry_proportions"]["Limestone"] > 70

    def test_bogue_phases_present(self):
        result = calculate_rawmix(solve_payload())
        phases = result["phases"]
        assert set(phases) == {"C3S", "C2S", "C3A", "C4AF"}
        assert phases["C3S"] > 50  # typical OPC clinker

    def test_src_uses_iron_ore_label(self):
        result = calculate_rawmix(solve_payload(cement_type="SRC"))
        assert result["corrector_label"] == "Iron Ore"
        assert "Iron Ore" in result["dry_proportions"]

    def test_opc_uses_slag_label(self):
        result = calculate_rawmix(solve_payload(cement_type="OPC"))
        assert result["corrector_label"] == "Slag"

    def test_feasible_solution_reported(self):
        result = calculate_rawmix(solve_payload())
        assert result["feasibility"] == "feasible"
        assert result["solve_method"] == "exact"
        for k in ("LSF", "SM", "AM"):
            assert result["residuals"][k] == pytest.approx(0.0, abs=0.5)

    def test_impossible_target_infeasible_not_negative(self):
        # AM=0.1 with these materials is physically impossible → constrained
        # fallback must return non-negative proportions + infeasible status.
        payload = solve_payload(targets={"LSF": 95.0, "SM": 2.4, "AM": 0.1})
        result = calculate_rawmix(payload)
        assert all(v >= 0 for v in result["dry_proportions"].values())
        assert result["feasibility"] == "infeasible"
        assert result["solve_method"] == "constrained"
        assert abs(result["residuals"]["AM"]) > 0.05  # target missed, reported
        assert "Not Simultaneously Reachable" in result["explanation"]
        assert result["dry_proportions"]["Clay"] == 0.0  # bounded at 0, not negative


class TestRecipeMode:
    def test_recipe_valid(self):
        payload = {
            "mode": "recipe",
            "cement_type": "OPC",
            "materials": BASE_MATERIALS,
            "hfo": HFO,
            "recipe": {"limestone": 78, "shale": 18, "sand": 2, "pyrite": 2},
        }
        result = calculate_rawmix(payload)
        assert result["dry_proportions"]["Limestone"] == pytest.approx(78.0, abs=1.0)

    def test_recipe_sum_rejected(self):
        payload = {
            "mode": "recipe",
            "cement_type": "OPC",
            "materials": BASE_MATERIALS,
            "hfo": HFO,
            "recipe": {"limestone": 50, "shale": 10, "sand": 1, "pyrite": 1},
        }
        with pytest.raises(ValueError, match="~100"):
            calculate_rawmix(payload)

    def test_recipe_rejects_negative_proportion(self):
        payload = {
            "mode": "recipe",
            "cement_type": "OPC",
            "materials": BASE_MATERIALS,
            "hfo": HFO,
            "recipe": {"limestone": 110, "shale": -10, "sand": 0, "pyrite": 0},
        }
        with pytest.raises(ValueError, match="non-negative"):
            calculate_rawmix(payload)

    def test_recipe_accepts_zero_proportion(self):
        payload = {
            "mode": "recipe",
            "cement_type": "OPC",
            "materials": BASE_MATERIALS,
            "hfo": HFO,
            "recipe": {"limestone": 0, "shale": 80, "sand": 10, "pyrite": 10},
        }
        result = calculate_rawmix(payload)
        assert result["dry_proportions"]["Limestone"] == 0.0

    def test_recipe_evaluation_gives_advice(self):
        payload = {
            "mode": "recipe",
            "cement_type": "OPC",
            "materials": BASE_MATERIALS,
            "hfo": HFO,
            "recipe": {"limestone": 80, "shale": 15, "sand": 3, "pyrite": 2},
        }
        result = calculate_rawmix(payload)
        assert "Adjustment" in result["explanation"] or "typical ranges" in result["explanation"]


class TestInputValidation:
    def test_missing_material_raises(self):
        payload = solve_payload()
        # Copy materials so the shared BASE_MATERIALS constant is NOT mutated
        payload["materials"] = {k: dict(v) for k, v in payload["materials"].items()}
        del payload["materials"]["sand"]
        with pytest.raises(ValueError, match="Missing materials"):
            calculate_rawmix(payload)

    def test_nan_oxide_rejected(self):
        mats = {k: dict(v) for k, v in BASE_MATERIALS.items()}
        mats["shale"]["SiO2"] = float("nan")
        payload = solve_payload()
        payload["materials"] = mats
        with pytest.raises(ValueError, match="finite"):
            calculate_rawmix(payload)

    def test_infinite_oxide_rejected(self):
        mats = {k: dict(v) for k, v in BASE_MATERIALS.items()}
        mats["limestone"]["CaO"] = float("inf")
        payload = solve_payload()
        payload["materials"] = mats
        with pytest.raises(ValueError, match="finite"):
            calculate_rawmix(payload)

    def test_loi_out_of_range_rejected(self):
        mats = {k: dict(v) for k, v in BASE_MATERIALS.items()}
        mats["sand"]["LOI"] = -5.0
        payload = solve_payload()
        payload["materials"] = mats
        with pytest.raises(ValueError, match="LOI"):
            calculate_rawmix(payload)

    def test_zero_calorific_rejected(self):
        payload = solve_payload()
        payload["hfo"] = {"heat": 730, "calorific": 0, "sulfur": 2.5}
        with pytest.raises(ValueError, match="calorific"):
            calculate_rawmix(payload)

    def test_negative_target_rejected(self):
        payload = solve_payload(targets={"LSF": -5.0, "SM": 2.4, "AM": 1.5})
        with pytest.raises(ValueError, match="positive"):
            calculate_rawmix(payload)

    def test_unknown_material_field_rejected(self):
        mats = {k: dict(v) for k, v in BASE_MATERIALS.items()}
        mats["shale"]["bogus"] = 1.0
        payload = solve_payload()
        payload["materials"] = mats
        with pytest.raises(ValueError, match="invalid fields"):
            calculate_rawmix(payload)

    def test_zero_fe2o3_materials_safe(self):
        # Sand with Fe2O3=0 must not crash the AM calc
        mats = {k: dict(v) for k, v in BASE_MATERIALS.items()}
        mats["sand"]["Fe2O3"] = 0.0
        payload = {
            "mode": "recipe",
            "cement_type": "OPC",
            "materials": mats,
            "hfo": HFO,
            "recipe": {"limestone": 78, "shale": 18, "sand": 2, "pyrite": 2},
        }
        result = calculate_rawmix(payload)
        assert "AM" in result["clinker"]


class TestPlantBenchmark:
    def test_rawmix_design_4_elements_benchmark(self):
        """Independently verifies the 4-material benchmark against rawmix/raw-mix-design-4 elemts.xlsx.
        
        Workbook targets: LSF 99.0, SM 2.4, AM 1.6 (no fuel ash/sulfur).
        Workbook unrounded proportions:
          Limestone: 82.4776%
          Shale: 13.7854%
          Iron Ore: 0.6482%
          Bauxite: 3.0888%
        """
        materials = {
            "limestone": {"SiO2": 3.24, "Al2O3": 0.79, "Fe2O3": 0.38, "CaO": 51.0, "MgO": 1.24, "K2O": 0.50, "Na2O": 0.20, "SO3": 0.10, "LOI": 42.48, "H2O": 0.0},
            "shale": {"SiO2": 74.98, "Al2O3": 8.80, "Fe2O3": 6.20, "CaO": 0.98, "MgO": 0.24, "K2O": 0.30, "Na2O": 0.20, "SO3": 0.20, "LOI": 8.00, "H2O": 0.0},
            "pyrite": {"SiO2": 9.16, "Al2O3": 2.00, "Fe2O3": 83.04, "CaO": 0.06, "MgO": 0.41, "K2O": 0.20, "Na2O": 0.10, "SO3": 0.07, "LOI": 4.65, "H2O": 0.0},
            "sand": {"SiO2": 9.00, "Al2O3": 50.00, "Fe2O3": 14.00, "CaO": 5.50, "MgO": 0.50, "K2O": 0.10, "Na2O": 0.10, "SO3": 0.05, "LOI": 21.00, "H2O": 0.0},
        }

        payload = {
            "mode": "solve",
            "cement_type": "OPC",
            "materials": materials,
            "targets": {"LSF": 99.0, "SM": 2.4, "AM": 1.6},
            "hfo": {"heat": 0, "calorific": 9800, "sulfur": 0.0},
        }

        result = calculate_rawmix(payload)

        assert result["feasibility"] == "feasible"
        props = result["dry_proportions"]

        # Within 0.1% tolerance of the plant workbook proportions
        assert props["Limestone"] == pytest.approx(82.48, abs=0.1)
        assert props["Clay"] == pytest.approx(13.79, abs=0.1)
        assert props["Slag"] == pytest.approx(0.65, abs=0.1)  # Iron Ore / Pyrite
        assert props["Sand"] == pytest.approx(3.09, abs=0.1)  # Bauxite corrector

        # Four proportions rounded to two decimals can differ from 100 by 0.02.
        assert sum(props.values()) == pytest.approx(100.0, abs=0.02)

        # Resulting clinker moduli match targets
        clinker = result["clinker"]
        assert clinker["LSF"] == pytest.approx(99.0, abs=0.1)
        assert clinker["SM"] == pytest.approx(2.4, abs=0.05)
        assert clinker["AM"] == pytest.approx(1.6, abs=0.05)

class TestPredefinedPresets:
    """Verifies the predefined frontend presets for OPC, SBC, and SRC."""

    LIMESTONE = {"SiO2": 1.62, "Al2O3": 0.44, "Fe2O3": 0.41, "CaO": 53.51, "MgO": 1.49, "Na2O": 0.02, "K2O": 0.12, "SO3": 0.08, "LOI": 42.41, "H2O": 5.0}
    CLAY = {"SiO2": 47.96, "Al2O3": 11.82, "Fe2O3": 6.08, "CaO": 12.98, "MgO": 3.73, "Na2O": 0.32, "K2O": 1.51, "SO3": 0.11, "LOI": 15.08, "H2O": 8.5}
    SAND = {"SiO2": 87.89, "Al2O3": 4.50, "Fe2O3": 2.75, "CaO": 0.71, "MgO": 0.92, "Na2O": 0.16, "K2O": 0.15, "SO3": 0.18, "LOI": 2.23, "H2O": 3.3}
    SLAG = {"SiO2": 23.60, "Al2O3": 8.25, "Fe2O3": 27.69, "CaO": 32.15, "MgO": 5.93, "Na2O": 0.20, "K2O": 0.50, "SO3": 1.50, "LOI": 0.90, "H2O": 6.5}
    IRON_ORE = {"SiO2": 49.00, "Al2O3": 0.69, "Fe2O3": 37.18, "CaO": 1.00, "MgO": 0.90, "Na2O": 0.29, "K2O": 0.81, "SO3": 1.50, "LOI": 8.55, "H2O": 7.8}
    HFO = {"heat": 730, "calorific": 9800, "sulfur": 2.5}

    @pytest.mark.parametrize("cement_type,corrector,targets,recipe", [
        ("OPC", SLAG, {"LSF": 95.0, "SM": 2.35, "AM": 1.40}, {"limestone": 72.32, "shale": 24.92, "sand": 0.37, "pyrite": 2.39}),
        ("SBC", SLAG, {"LSF": 94.0, "SM": 2.35, "AM": 1.40}, {"limestone": 72.06, "shale": 25.16, "sand": 0.37, "pyrite": 2.42}),
        ("SRC", IRON_ORE, {"LSF": 95.0, "SM": 2.25, "AM": 0.80}, {"limestone": 74.15, "shale": 19.97, "sand": 0.75, "pyrite": 5.13}),
    ])
    def test_preset_solve_mode(self, cement_type, corrector, targets, recipe):
        materials = {
            "limestone": self.LIMESTONE,
            "shale": self.CLAY,
            "sand": self.SAND,
            "pyrite": corrector,
        }
        payload = {
            "mode": "solve",
            "cement_type": cement_type,
            "materials": materials,
            "targets": targets,
            "hfo": self.HFO,
        }
        res = calculate_rawmix(payload)
        assert res["feasibility"] in {"feasible", "valid"}
        assert not any(d["severity"] == "error" for d in res["diagnostics"])
        
        # Verify clinker moduli reach target setpoints
        cl = res["clinker"]
        assert cl["LSF"] == pytest.approx(targets["LSF"], abs=0.1)
        assert cl["SM"] == pytest.approx(targets["SM"], abs=0.05)
        assert cl["AM"] == pytest.approx(targets["AM"], abs=0.05)
        
        # For SRC, C3A must satisfy sulfate-resistance ASTM C150 standard (<= 5.0%)
        if cement_type == "SRC":
            assert res["phases"]["C3A"] <= 5.0

    @pytest.mark.parametrize("cement_type,corrector,targets,recipe", [
        ("OPC", SLAG, {"LSF": 95.0, "SM": 2.35, "AM": 1.40}, {"limestone": 72.32, "shale": 24.92, "sand": 0.37, "pyrite": 2.39}),
        ("SBC", SLAG, {"LSF": 94.0, "SM": 2.35, "AM": 1.40}, {"limestone": 72.06, "shale": 25.16, "sand": 0.37, "pyrite": 2.42}),
        ("SRC", IRON_ORE, {"LSF": 95.0, "SM": 2.25, "AM": 0.80}, {"limestone": 74.15, "shale": 19.97, "sand": 0.75, "pyrite": 5.13}),
    ])
    def test_preset_recipe_mode(self, cement_type, corrector, targets, recipe):
        materials = {
            "limestone": self.LIMESTONE,
            "shale": self.CLAY,
            "sand": self.SAND,
            "pyrite": corrector,
        }
        payload = {
            "mode": "recipe",
            "cement_type": cement_type,
            "materials": materials,
            "recipe": recipe,
            "hfo": self.HFO,
        }
        res = calculate_rawmix(payload)
        assert res["feasibility"] in {"feasible", "valid"}
        assert not any(d["severity"] == "error" for d in res["diagnostics"])
        cl = res["clinker"]
        assert cl["LSF"] == pytest.approx(targets["LSF"], abs=0.2)
        assert cl["SM"] == pytest.approx(targets["SM"], abs=0.05)
        assert cl["AM"] == pytest.approx(targets["AM"], abs=0.05)

    def test_economics_calorific_comparison_sinoma_baseline(self):
        materials = {
            "limestone": self.LIMESTONE,
            "shale": self.CLAY,
            "sand": self.SAND,
            "pyrite": self.SLAG,
        }
        # Baseline at 9800 kcal/kg
        payload_base = {
            "mode": "solve",
            "cement_type": "OPC",
            "materials": materials,
            "targets": {"LSF": 95.0, "SM": 2.35, "AM": 1.40},
            "hfo": {"heat": 740, "calorific": 9800, "sulfur": 2.5},
            "economics": {
                "currency": "$",
                "fuel_price_per_ton": 350.0,
                "plant_capacity_tpd": 5300.0,
                "operating_days_per_year": 310.0,
            },
        }
        res_base = calculate_rawmix(payload_base)
        econ_base = res_base["economics"]
        assert econ_base["fuel"]["status"] == "standard"
        assert econ_base["fuel"]["sfc_actual_kg_t"] == pytest.approx(75.51, abs=0.05)
        assert econ_base["fuel"]["sfc_var_kg_t"] == pytest.approx(0.0, abs=0.05)
        assert econ_base["fuel"]["cost_var_per_t_clinker"] == pytest.approx(0.0, abs=0.05)

        # Dropped calorific to 9200 kcal/kg (user scenario)
        payload_low = {
            "mode": "solve",
            "cement_type": "OPC",
            "materials": materials,
            "targets": {"LSF": 95.0, "SM": 2.35, "AM": 1.40},
            "hfo": {"heat": 740, "calorific": 9200, "sulfur": 2.5},
            "economics": {
                "currency": "$",
                "fuel_price_per_ton": 350.0,
                "plant_capacity_tpd": 5300.0,
                "operating_days_per_year": 310.0,
            },
        }
        res_low = calculate_rawmix(payload_low)
        econ_low = res_low["economics"]
        assert econ_low["fuel"]["status"] == "penalty"
        assert econ_low["fuel"]["calorific_deficit"] == 600.0
        # SFC rises to ~80.43 kg/t (+4.92 kg/t or +6.52%)
        assert econ_low["fuel"]["sfc_actual_kg_t"] == pytest.approx(80.43, abs=0.05)
        assert econ_low["fuel"]["sfc_var_kg_t"] == pytest.approx(4.92, abs=0.05)
        assert econ_low["fuel"]["sfc_var_pct"] == pytest.approx(6.52, abs=0.1)
        # Cost variance per ton clinker: ~ +$1.72/t
        assert econ_low["fuel"]["cost_var_per_t_clinker"] == pytest.approx(1.72, abs=0.05)
        # Extra fuel tons/day: ~ +26.1 tons/day
        assert econ_low["fuel"]["daily_fuel_var_t"] == pytest.approx(26.1, abs=0.2)
        # Daily cost penalty: ~ +$9,135/day
        assert econ_low["fuel"]["daily_cost_var"] == pytest.approx(9135.0, abs=50.0)
        # Warning diagnostic generated
        assert any("below Sinoma design standard" in d["message"] for d in res_low["diagnostics"])

