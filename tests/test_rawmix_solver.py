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
