"""FLS 4×4 raw mix proportion solver (server-side, shared with dashboard API)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chemistry import BoguePhases, OxideAnalysis, calc_liquid_content, clinker_lsf_percent, rawmix_diagnostics


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
DISPLAY_NAMES = {
    "limestone": "Limestone",
    "shale": "Clay",
    "sand": "Sand",
    "pyrite": "Slag",  # overridden for SRC → Iron Ore
}


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


def calculate_rawmix(payload: dict[str, Any]) -> dict[str, Any]:
    mode = payload.get("mode", "solve")
    cement_type = payload.get("cement_type", "OPC")
    is_slag = cement_type in ("OPC", "SBC")
    corrector_label = "Slag" if is_slag else "Iron Ore"

    materials = {
        key: MaterialComp(**payload["materials"][key])
        for key in MATERIAL_NAMES
    }
    hfo = payload.get("hfo", {})
    hfo_heat = float(hfo.get("heat", 730))
    hfo_cal = float(hfo.get("calorific", 9800))
    hfo_sulfur = float(hfo.get("sulfur", 2.5))

    cl_so3_fuel = _fuel_so3(hfo_heat, hfo_cal, hfo_sulfur)
    cl_basis = _clinker_basis(materials)
    x5 = 0.0

    if mode == "solve":
        targets = payload["targets"]
        target_lsf = float(targets["LSF"])
        target_sm = float(targets["SM"])
        target_am = float(targets["AM"])

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
        if X is None:
            raise ValueError(
                "Solver encountered a mathematical error (singular matrix). "
                "Review material compositions."
            )
        x_cl = X + [x5]
    else:
        recipe = payload["recipe"]
        p = [float(recipe[n]) for n in MATERIAL_NAMES]
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

    c3s = 4.071 * (cao - 0.7 * cl_so3_total) - 7.600 * sio2 - 6.718 * al2o3 - 1.430 * fe2o3
    c2s = 2.867 * sio2 - 0.7544 * c3s
    c3a = 2.650 * al2o3 - 1.692 * fe2o3
    c4af = 3.043 * fe2o3
    phases = BoguePhases(C3S=c3s, C2S=c2s, C3A=c3a, C4AF=c4af)
    ox_clinker = OxideAnalysis(MgO=mgo, Na2O=na2o, K2O=k2o)
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
    diagnostics = rawmix_diagnostics(cement_type, cl_lsf, cl_sm, cl_am, c3a, lc)

    # Generate Explanation
    explanation_parts = []
    has_negatives = any(v < 0 for v in x_dry)

    if has_negatives:
        diagnostics.insert(0, {
            "severity": "error", 
            "message": "Calculated raw mix requires physically impossible negative proportions."
        })


    if mode == "solve":
        if has_negatives:
            neg_mats = [labels[i] for i in range(4) if x_dry[i] < 0]
            explanation_parts.append(
                f"🚨 **Impossible Target:** The solver reached the target moduli mathematically, but it required **NEGATIVE** proportions for: {', '.join(neg_mats)}."
            )
            if "Sand" in neg_mats:
                explanation_parts.append(
                    f"<br><strong>Why?</strong> Your Iron Ore (or Clay) likely contains too much Silica (SiO₂) to reach your low AM target without overshooting your SM target. "
                    f"To fix this, you must either increase your target SM, increase your target AM, or use a purer Iron Ore (with lower SiO₂)."
                )
            elif "Pyrite" in neg_mats or "Clay" in neg_mats:
                explanation_parts.append(
                    f"<br><strong>Why?</strong> Your other materials already provide more of certain oxides (like Fe₂O₃ or Al₂O₃) than needed. Try adjusting your target AM or SM."
                )
            else:
                explanation_parts.append("<br><strong>Why?</strong> The requested moduli contradict the natural chemistry of your raw materials.")
        else:
            explanation_parts.append("✅ **Mathematically Valid Mix:**")
            explanation_parts.append(f"<ul><li><strong>Limestone</strong> provides the majority of the CaO to hit LSF {target_lsf}.</li>")
            explanation_parts.append(f"<li><strong>Clay</strong> acts as the primary source of Alumina and Silica.</li>")
            explanation_parts.append(f"<li><strong>Sand</strong> balances the Silica Modulus (SM) to {target_sm}.</li>")
            explanation_parts.append(f"<li><strong>Iron Ore/Pyrite</strong> adjusts the Alumina Modulus (AM) to {target_am}.</li></ul>")
    else:
        explanation_parts.append("ℹ️ **Recipe Calculation:** Proportions were manually provided.")
        if has_negatives:
            explanation_parts.append("<br><strong>Warning:</strong> You entered negative proportions.")

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
            "C3S": round(c3s, 1),
            "C2S": round(c2s, 1),
            "C3A": round(c3a, 1),
            "C4AF": round(c4af, 1),
        },
        "liquid_content": round(lc, 1),
        "diagnostics": diagnostics,
        "corrector_label": corrector_label,
        "explanation": "".join(explanation_parts),
    }
