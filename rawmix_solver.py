"""FLS 4×4 raw mix proportion solver (server-side, shared with dashboard API).

Exact target matching when a non-negative solution exists; otherwise a
bounded least-squares fallback that reports residuals and infeasibility
instead of returning physically impossible negative proportions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from scipy.optimize import minimize

from chemistry import (
    OxideAnalysis,
    calc_bogue,
    calc_liquid_content,
    clinker_lsf_percent,
    rawmix_diagnostics,
)


@dataclass
class MaterialComp:
    SiO2: float
    Al2O3: float
    Fe2O3: float
    CaO: float
    MgO: float = 0.0
    Na2O: float = 0.0
    K2O: float = 0.0
    SO3: float = 0.0
    LOI: float = 0.0
    H2O: float = 0.0


MATERIAL_NAMES = ["limestone", "shale", "sand", "pyrite"]

_OXIDE_FIELDS = ("SiO2", "Al2O3", "Fe2O3", "CaO", "MgO", "Na2O", "K2O", "SO3")


def _validate_materials(materials: dict[str, Any]) -> dict[str, MaterialComp]:
    missing = [n for n in MATERIAL_NAMES if n not in materials]
    if missing:
        raise ValueError(f"Missing materials: {', '.join(missing)}")
    comps = {}
    for name in MATERIAL_NAMES:
        try:
            comp = MaterialComp(**materials[name])
        except TypeError as e:
            raise ValueError(f"Material '{name}' has invalid fields: {e}") from e
        for field in _OXIDE_FIELDS:
            if not math.isfinite(getattr(comp, field)):
                raise ValueError(f"Material '{name}' {field} must be a finite number.")
        if not 0 <= comp.LOI < 100:
            raise ValueError(f"Material '{name}' LOI must be in [0, 100).")
        if not 0 <= comp.H2O < 100:
            raise ValueError(f"Material '{name}' H2O must be in [0, 100).")
        comps[name] = comp
    return comps


def _validate_hfo(hfo: dict[str, Any]) -> tuple[float, float, float]:
    heat = float(hfo.get("heat", 730))
    calorific = float(hfo.get("calorific", 9800))
    sulfur = float(hfo.get("sulfur", 2.5))
    for name, v in (("heat", heat), ("calorific", calorific), ("sulfur", sulfur)):
        if not math.isfinite(v):
            raise ValueError(f"hfo {name} must be a finite number.")
    if calorific <= 0:
        raise ValueError("hfo calorific value must be greater than 0.")
    if not 0 <= sulfur <= 100:
        raise ValueError("hfo sulfur must be in [0, 100].")
    return heat, calorific, sulfur


def _validate_targets(targets: dict[str, Any]) -> tuple[float, float, float]:
    try:
        lsf = float(targets["LSF"])
        sm = float(targets["SM"])
        am = float(targets["AM"])
    except KeyError as e:
        raise ValueError(f"Missing target {e.args[0]}.") from e
    for name, v in (("LSF", lsf), ("SM", sm), ("AM", am)):
        if not math.isfinite(v) or v <= 0:
            raise ValueError(f"Target {name} must be a positive finite number.")
    return lsf, sm, am


def _validate_recipe(recipe: dict[str, Any]) -> list[float]:
    p = []
    for name in MATERIAL_NAMES:
        try:
            v = float(recipe[name])
        except KeyError as e:
            raise ValueError(f"Missing recipe material '{name}'.") from e
        if not math.isfinite(v):
            raise ValueError(f"Recipe {name} must be a finite number.")
        if v < 0:
            raise ValueError(f"Recipe {name} must be non-negative.")
        p.append(v)
    return p


def _solve4x4(matrix: list[list[float]], constants: list[float]) -> list[float] | None:
    n = 4
    a = [row[:] for row in matrix]
    b = constants[:]

    for i in range(n):
        max_row = i
        for k in range(i + 1, n):
            if abs(a[k][i]) > abs(a[max_row][i]):
                max_row = k
        a[i], a[max_row] = a[max_row], a[i]
        b[i], b[max_row] = b[max_row], b[i]

        if abs(a[i][i]) < 1e-12:
            return None

        for k in range(i + 1, n):
            factor = a[k][i] / a[i][i]
            for j in range(i, n):
                a[k][j] -= factor * a[i][j]
            b[k] -= factor * b[i]

    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = b[i] - sum(a[i][j] * x[j] for j in range(i + 1, n))
        x[i] = s / a[i][i]
    return x


def _clinker_basis(materials: dict[str, MaterialComp]) -> dict[str, dict[str, float]]:
    cl_basis = {}
    for name, comp in materials.items():
        factor = 1.0 - 0.01 * comp.LOI
        if factor <= 0:
            raise ValueError(f"LOI for {name} must be less than 100%.")
        cl_basis[name] = {
            "SiO2": comp.SiO2 / factor,
            "Al2O3": comp.Al2O3 / factor,
            "Fe2O3": comp.Fe2O3 / factor,
            "CaO": comp.CaO / factor,
            "MgO": comp.MgO / factor,
            "Na2O": comp.Na2O / factor,
            "K2O": comp.K2O / factor,
            "SO3": comp.SO3 / factor,
        }
    return cl_basis


def _fuel_so3(hfo_heat: float, hfo_cal: float, hfo_sulfur: float) -> float:
    return (hfo_heat / hfo_cal) * hfo_sulfur * 2.25


def _solve_constrained(
    deltas: dict[str, dict[str, float]],
    b_targets: list[float],
    x0: list[float] | None = None,
) -> list[float]:
    """Closest feasible mix: least-squares on the modulus equations,
    bounded to non-negative proportions summing to 100. Warm-started from
    the clipped exact solution so SLSQP lands in the right basin."""

    def objective(x: list[float]) -> float:
        keys = ("dC", "dS", "dA")
        residuals = [
            sum(x[i] * deltas[n][keys[k]] for i, n in enumerate(MATERIAL_NAMES)) - b
            for k, b in enumerate(b_targets)
        ]
        return sum(v * v for v in residuals)

    start = [min(max(v, 0.0), 100.0) for v in x0] if x0 else [25.0] * 4
    cons = {"type": "eq", "fun": lambda x: sum(x) - 100.0}
    res = minimize(
        objective,
        start,
        method="SLSQP",
        bounds=[(0.0, 100.0)] * 4,
        constraints=[cons],
    )
    if not res.success:
        raise ValueError("Could not find a valid raw mix — review material chemistry and targets.")
    return [max(0.0, v) for v in res.x]


def calculate_rawmix(payload: dict[str, Any]) -> dict[str, Any]:
    mode = payload.get("mode", "solve")
    if mode == "calc":
        mode = "recipe"
    cement_type = payload.get("cement_type", "OPC")
    is_slag = cement_type in ("OPC", "SBC")
    corrector_label = "Slag" if is_slag else "Iron Ore"

    materials = _validate_materials(payload.get("materials", {}))
    hfo_heat, hfo_cal, hfo_sulfur = _validate_hfo(payload.get("hfo", {}))

    cl_so3_fuel = _fuel_so3(hfo_heat, hfo_cal, hfo_sulfur)
    cl_basis = _clinker_basis(materials)
    x5 = 0.0

    if mode == "solve":
        target_lsf, target_sm, target_am = _validate_targets(payload["targets"])

        def calc_deltas(comp: dict[str, float]) -> dict[str, float]:
            c, s, a, f, so3 = comp["CaO"], comp["SiO2"], comp["Al2O3"], comp["Fe2O3"], comp["SO3"]
            return {
                "dC": c - 0.7 * so3 - 0.01 * target_lsf * (2.8 * s + 1.18 * a + 0.65 * f),
                "dS": s - target_sm * (a + f),
                "dA": a - target_am * f,
            }

        deltas = {name: calc_deltas(cl_basis[name]) for name in MATERIAL_NAMES}
        M = [
            [deltas[n]["dC"] for n in MATERIAL_NAMES],
            [deltas[n]["dS"] for n in MATERIAL_NAMES],
            [deltas[n]["dA"] for n in MATERIAL_NAMES],
            [1.0, 1.0, 1.0, 1.0],
        ]
        B = [70.0 * cl_so3_fuel, 0.0, 0.0, 100.0]
        X = _solve4x4(M, B)
        if X is not None and all(v >= -1e-9 for v in X):
            x_cl = X + [x5]
            solve_method = "exact"
        else:
            x_cl = _solve_constrained(deltas, B[:3], X) + [x5]
            solve_method = "constrained"
    else:
        p = _validate_recipe(payload["recipe"])
        recipe_sum = sum(p)
        if recipe_sum < 99.0 or recipe_sum > 101.0:
            raise ValueError(f"Recipe proportions sum to {recipe_sum:.2f}% — must be ~100%.")

        x_dry_norm = [(v / recipe_sum) * 100.0 for v in p]
        c_dry = [
            x_dry_norm[i] * (1.0 - 0.01 * materials[MATERIAL_NAMES[i]].LOI)
            for i in range(4)
        ]
        total_cl = sum(c_dry)
        x_cl = [(c_dry[i] / total_cl) * (100.0 - x5) for i in range(4)] + [x5]

    clinker_chem: dict[str, float] = {}
    for oxide in ("SiO2", "Al2O3", "Fe2O3", "CaO", "MgO", "Na2O", "K2O", "SO3"):
        val = sum(x_cl[i] * cl_basis[MATERIAL_NAMES[i]][oxide] for i in range(4))
        clinker_chem[oxide] = val / 100.0

    cao = clinker_chem["CaO"]
    sio2 = clinker_chem["SiO2"]
    al2o3 = clinker_chem["Al2O3"]
    fe2o3 = clinker_chem["Fe2O3"]
    mgo = clinker_chem["MgO"]
    na2o = clinker_chem["Na2O"]
    k2o = clinker_chem["K2O"]
    cl_so3_raw = clinker_chem["SO3"]
    cl_so3_total = cl_so3_raw + cl_so3_fuel

    cl_lsf = clinker_lsf_percent(cao, sio2, al2o3, fe2o3, cl_so3_total)
    cl_sm = sio2 / (al2o3 + fe2o3) if (al2o3 + fe2o3) else 0.0
    cl_am = al2o3 / fe2o3 if fe2o3 else 0.0

    ox_clinker = OxideAnalysis(
        SiO2=sio2, Al2O3=al2o3, Fe2O3=fe2o3, CaO=cao, MgO=mgo,
        Na2O=na2o, K2O=k2o, SO3=cl_so3_total,
    )
    phases = calc_bogue(ox_clinker)
    lc = calc_liquid_content(phases, ox_clinker)

    x_dry = [
        x_cl[i] / (1.0 - 0.01 * materials[MATERIAL_NAMES[i]].LOI) for i in range(4)
    ]
    sum_dry = sum(x_dry)
    x_dry_norm = [(v / sum_dry) * 100.0 for v in x_dry]

    x_wet = [
        x_dry_norm[i] / (1.0 - 0.01 * materials[MATERIAL_NAMES[i]].H2O) for i in range(4)
    ]
    sum_wet = sum(x_wet)
    x_wet_norm = [(v / sum_wet) * 100.0 for v in x_wet]

    labels = ["Limestone", "Clay", "Sand", corrector_label]
    diagnostics = rawmix_diagnostics(cement_type, cl_lsf, cl_sm, cl_am, phases.C3A, lc)

    residuals = None
    feasibility = "valid"
    if mode == "solve":
        residuals = {
            "LSF": round(target_lsf - cl_lsf, 2),
            "SM": round(target_sm - cl_sm, 3),
            "AM": round(target_am - cl_am, 3),
        }
        tolerances = {"LSF": 0.2, "SM": 0.05, "AM": 0.05}
        feasibility = (
            "feasible"
            if all(abs(residuals[k]) <= tolerances[k] for k in tolerances)
            else "infeasible"
        )
        if feasibility == "infeasible":
            diagnostics.insert(0, {
                "severity": "error",
                "message": (
                    f"Targets are not simultaneously reachable with these materials — "
                    f"closest achievable mix shown (LSF residual {residuals['LSF']:+0.2f}, "
                    f"SM {residuals['SM']:+0.2f}, AM {residuals['AM']:+0.2f})."
                ),
            })

    # Generate Explanation
    explanation_parts = []

    negative_phases = [
        n for n, v in (
            ("C3S", phases.C3S), ("C2S", phases.C2S),
            ("C3A", phases.C3A), ("C4AF", phases.C4AF),
        ) if v < 0
    ]
    if negative_phases:
        diagnostics.insert(0, {
            "severity": "error",
            "message": (
                f"Clinker chemistry is physically impossible: negative Bogue phases "
                f"({', '.join(negative_phases)}). Review target moduli and material chemistry."
            ),
        })


    if mode == "solve":
        if feasibility == "infeasible":
            explanation_parts.append(
                f"🚨 **Targets Not Simultaneously Reachable:** residuals LSF {residuals['LSF']:+0.2f}, "
                f"SM {residuals['SM']:+0.2f}, AM {residuals['AM']:+0.2f} — showing the closest achievable mix."
            )
            explanation_parts.append(
                "<br><strong>Why?</strong> The requested moduli contradict the natural chemistry of your raw materials. "
                "Adjust the targets or the material chemistry (e.g. a purer iron source with lower SiO₂)."
            )
        else:
            explanation_parts.append("✅ **Mathematically Valid Mix:**")
            explanation_parts.append(f"<ul><li><strong>Limestone</strong> provides the majority of the CaO to hit LSF {target_lsf}.</li>")
            explanation_parts.append(f"<li><strong>Clay</strong> acts as the primary source of Alumina and Silica.</li>")
            explanation_parts.append(f"<li><strong>Sand</strong> balances the Silica Modulus (SM) to {target_sm}.</li>")
            explanation_parts.append(f"<li><strong>Iron Ore/Pyrite</strong> adjusts the Alumina Modulus (AM) to {target_am}.</li></ul>")
    else:
        targets_advice = []
        if cement_type == "SRC":
            if cl_lsf > 96.0:
                targets_advice.append(f"LSF ({cl_lsf:.1f}%) is above 96% — reduce Limestone or increase SiO₂ to avoid hard burning.")
            elif cl_lsf < 90.0:
                targets_advice.append(f"LSF ({cl_lsf:.1f}%) is low — increase Limestone to boost C₃S and 28-day strength.")
            if cl_am > 1.0:
                targets_advice.append(f"AM ({cl_am:.2f}) exceeds 1.0 — reduce Clay or increase Iron Ore to lower C₃A for SRC compliance.")
            if cl_sm > 3.0:
                targets_advice.append(f"SM ({cl_sm:.2f}) is high — add more Clay or reduce Sand to improve burnability.")
            elif cl_sm < 2.0:
                targets_advice.append(f"SM ({cl_sm:.2f}) is low — add Sand to increase liquid phase viscosity.")
        else:
            if cl_lsf > 97.0:
                targets_advice.append(f"LSF ({cl_lsf:.1f}%) exceeds 97% — reduce Limestone or increase SiO₂ to prevent free lime.")
            elif cl_lsf < 92.0:
                targets_advice.append(f"LSF ({cl_lsf:.1f}%) is below 92% — increase Limestone to improve strength potential.")
            if cl_am > 1.8:
                targets_advice.append(f"AM ({cl_am:.2f}) is high — increase Iron Ore supply (or reduce Clay) to lower liquid viscosity.")
            elif cl_am < 1.2:
                targets_advice.append(f"AM ({cl_am:.2f}) is low — reduce Iron Ore or increase Clay to avoid sticky coating.")
            if cl_sm > 2.8:
                targets_advice.append(f"SM ({cl_sm:.2f}) is high — add Clay or reduce Sand to improve burnability and coating.")
            elif cl_sm < 2.0:
                targets_advice.append(f"SM ({cl_sm:.2f}) is low — add Sand to increase liquid phase viscosity.")

        if targets_advice:
            explanation_parts.append("📊 **Recipe Evaluation & Adjustment Tips:**")
            explanation_parts.append("<ul>")
            for tip in targets_advice:
                explanation_parts.append(f"<li>{tip}</li>")
            explanation_parts.append("</ul>")
        else:
            explanation_parts.append("✅ **Recipe is within typical ranges.** No adjustments needed.")

        explanation_parts.append("<br><i>Tip: Switch to <strong>Solve for Target</strong> mode if you want the solver to automatically find proportions that hit specific LSF / SM / AM targets.</i>")

    return {
        "dry_proportions": {
            labels[i]: round(x_dry_norm[i], 2) for i in range(4)
        },
        "wet_proportions": {
            f"{labels[i]} (Y{i + 1})": round(x_wet_norm[i], 2) for i in range(4)
        },
        "clinker": {
            "SiO2": round(sio2, 2),
            "Al2O3": round(al2o3, 2),
            "Fe2O3": round(fe2o3, 2),
            "CaO": round(cao, 2),
            "MgO": round(mgo, 2),
            "Na2O": round(na2o, 2),
            "K2O": round(k2o, 2),
            "SO3": round(cl_so3_total, 2),
            "LSF": round(cl_lsf, 1),
            "SM": round(cl_sm, 2),
            "AM": round(cl_am, 2),
        },
        "phases": {
            "C3S": round(phases.C3S, 1),
            "C2S": round(phases.C2S, 1),
            "C3A": round(phases.C3A, 1),
            "C4AF": round(phases.C4AF, 1),
        },
        "liquid_content": round(lc, 1),
        "diagnostics": diagnostics,
        "corrector_label": corrector_label,
        "residuals": residuals,
        "feasibility": feasibility,
        "solve_method": solve_method if mode == "solve" else "recipe",
        "explanation": "".join(explanation_parts),
    }
