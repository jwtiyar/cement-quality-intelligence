"""FLS / plant-standard cement chemistry (single source of truth)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OxideAnalysis:
    SiO2: float = 0.0
    Al2O3: float = 0.0
    Fe2O3: float = 0.0
    CaO: float = 0.0
    MgO: float = 0.0
    SO3: float = 0.0
    Na2O: float = 0.0
    K2O: float = 0.0


@dataclass
class BoguePhases:
    C3S: float
    C2S: float
    C3A: float
    C4AF: float


@dataclass
class Moduli:
    LSF: float  # ratio (0–1), e.g. 0.98
    SM: float
    AM: float

    @property
    def LSF_percent(self) -> float:
        return self.LSF * 100.0


def calc_moduli(ox: OxideAnalysis) -> Moduli:
    denom = 2.8 * ox.SiO2 + 1.18 * ox.Al2O3 + 0.65 * ox.Fe2O3
    lsf = (ox.CaO - 0.7 * ox.SO3) / denom if denom else 0.0
    sm_denom = ox.Al2O3 + ox.Fe2O3
    sm = ox.SiO2 / sm_denom if sm_denom else 0.0
    am = ox.Al2O3 / ox.Fe2O3 if ox.Fe2O3 else 0.0
    return Moduli(LSF=lsf, SM=sm, AM=am)


def calc_bogue(ox: OxideAnalysis) -> BoguePhases:
    c3s = 4.071 * ox.CaO - 7.600 * ox.SiO2 - 6.718 * ox.Al2O3 - 1.430 * ox.Fe2O3 - 2.852 * ox.SO3
    c2s = 2.867 * ox.SiO2 - 0.7544 * c3s
    c3a = 2.650 * ox.Al2O3 - 1.692 * ox.Fe2O3
    c4af = 3.043 * ox.Fe2O3
    return BoguePhases(
        C3S=max(0.0, c3s),
        C2S=max(0.0, c2s),
        C3A=max(0.0, c3a),
        C4AF=max(0.0, c4af),
    )


def calc_liquid_content(phases: BoguePhases, ox: OxideAnalysis | None = None) -> float:
    """Lea & Parker liquid at 1400°C (%)."""
    ox = ox or OxideAnalysis()
    return (
        1.13 * phases.C3A
        + 1.35 * phases.C4AF
        + ox.MgO
        + ox.Na2O
        + 0.65 * ox.K2O
    )


def clinker_lsf_percent(cao: float, sio2: float, al2o3: float, fe2o3: float, so3: float) -> float:
    denom = 2.8 * sio2 + 1.18 * al2o3 + 0.65 * fe2o3
    if not denom:
        return 0.0
    return 100.0 * (cao - 0.7 * so3) / denom


def analyze_clinker(ox: OxideAnalysis) -> dict[str, Any]:
    mod = calc_moduli(ox)
    phases = calc_bogue(ox)
    lc = calc_liquid_content(phases, ox)
    return {
        "moduli": {
            "LSF": round(mod.LSF_percent, 2),
            "SM": round(mod.SM, 4),
            "AM": round(mod.AM, 4),
        },
        "phases": {
            "C3S": round(phases.C3S, 2),
            "C2S": round(phases.C2S, 2),
            "C3A": round(phases.C3A, 2),
            "C4AF": round(phases.C4AF, 2),
        },
        "liquid_content": round(lc, 2),
    }


def lsf_advice(lsf_percent: float) -> str:
    if lsf_percent < 92:
        return (
            f"Lime Saturation Factor is low ({lsf_percent:.1f}%). "
            "You can safely increase CaO in the raw mix to raise C3S and 28-day strength."
        )
    if lsf_percent <= 98:
        return (
            f"Lime Saturation Factor ({lsf_percent:.1f}%) is in an optimal zone. "
            "For more strength, focus on kiln temperature or finer grinding (Blaine)."
        )
    return (
        f"Lime Saturation Factor is high ({lsf_percent:.1f}%). "
        "Do NOT increase CaO — risk of free lime and expansion. Lower SiO2 or grind finer."
    )


def rawmix_diagnostics(
    cement_type: str,
    lsf_percent: float,
    sm: float,
    am: float,
    c3a: float,
    liquid_content: float,
) -> list[dict[str, str]]:
    """Return diagnostic messages for raw mix / clinker targets."""
    warnings: list[dict[str, str]] = []
    is_src = cement_type == "SRC"

    if is_src:
        if lsf_percent > 96.0:
            warnings.append({
                "severity": "warning",
                "message": (
                    f"Hard-Burning Risk: clinker LSF is high ({lsf_percent:.1f}%). "
                    "Sintering may need excessive temperatures (>1450°C)."
                ),
            })
        if am > 1.0:
            warnings.append({
                "severity": "warning",
                "message": (
                    f"High Alumina Modulus for SRC: AM {am:.2f} exceeds 1.0. "
                    "Lower AM is required to keep C3A low."
                ),
            })
    elif lsf_percent > 97.0:
        warnings.append({
            "severity": "warning",
            "message": (
                f"Hard-Burning Risk: clinker LSF is high ({lsf_percent:.1f}%). "
                "Sintering may need excessive temperatures (>1450°C)."
            ),
        })

    if is_src and c3a > 5.0:
        warnings.append({
            "severity": "error",
            "message": (
                f"SRC Compliance Failure: expected C3A is {c3a:.1f}% (limit 5.0% for ASTM C150 Type V). "
                "Increase iron ore or reduce alumina sources."
            ),
        })

    if liquid_content < 22.0 or sm > 2.8:
        warnings.append({
            "severity": "warning",
            "message": (
                f"Low Liquid / Sintering Difficulty: LC {liquid_content:.1f}% or SM {sm:.2f} "
                "may cause dusty clinker and poor nodulization."
            ),
        })
    elif liquid_content > 30.0 or sm < 2.0:
        warnings.append({
            "severity": "warning",
            "message": (
                f"High Liquid / Sticky Sintering: LC {liquid_content:.1f}% or SM {sm:.2f} "
                "may cause kiln rings and cooler blockages."
            ),
        })

    return warnings
