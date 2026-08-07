"""Pydantic request models for the API — strict, typed input validation."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChemistryAnalyzeRequest(BaseModel):
    SiO2: float = Field(ge=0, le=100)
    Al2O3: float = Field(ge=0, le=100)
    Fe2O3: float = Field(ge=0, le=100)
    CaO: float = Field(ge=0, le=100)
    MgO: float = Field(default=0.0, ge=0, le=100)
    Na2O: float = Field(default=0.0, ge=0, le=100)
    K2O: float = Field(default=0.0, ge=0, le=100)
    SO3: float = Field(default=0.0, ge=0, le=100)


class PredictRequest(BaseModel):
    Cement_Type: Literal["OPC", "SRC", "SBC"] = "OPC"
    # All feature values optional — missing features fall back to the
    # training-average for that cement type, as the app already does.
    SiO2: Optional[float] = None
    Al2O3: Optional[float] = None
    Fe2O3: Optional[float] = None
    CaO: Optional[float] = None
    MgO: Optional[float] = None
    SO3: Optional[float] = None
    Strength_Early: Optional[float] = None
    Early_Strength_Days: Optional[float] = None
    Fineness: Optional[float] = None
    Strength_7D: Optional[float] = None
    Residue_80: Optional[float] = None


class MaterialChemistry(BaseModel):
    SiO2: float = Field(ge=0, le=100)
    Al2O3: float = Field(ge=0, le=100)
    Fe2O3: float = Field(ge=0, le=100)
    CaO: float = Field(ge=0, le=100)
    MgO: float = Field(default=0.0, ge=0, le=100)
    Na2O: float = Field(default=0.0, ge=0, le=100)
    K2O: float = Field(default=0.0, ge=0, le=100)
    SO3: float = Field(default=0.0, ge=0, le=100)
    LOI: float = Field(default=0.0, ge=0, lt=100)
    H2O: float = Field(default=0.0, ge=0, lt=100)


class RawMixTargets(BaseModel):
    LSF: float = Field(gt=0)
    SM: float = Field(gt=0)
    AM: float = Field(gt=0)


class HFO(BaseModel):
    heat: float = Field(default=730, ge=0)
    calorific: float = Field(default=9800, gt=0)
    sulfur: float = Field(default=2.5, ge=0, le=100)


class RawMixRequest(BaseModel):
    mode: Literal["solve", "recipe"] = "solve"
    cement_type: Literal["OPC", "SRC", "SBC"] = "OPC"
    materials: dict[str, MaterialChemistry]
    targets: Optional[RawMixTargets] = None
    recipe: Optional[dict[str, float]] = None
    hfo: HFO = Field(default_factory=HFO)


class ChatTurn(BaseModel):
    role: Literal["user", "model"] = "user"
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatTurn] = Field(default_factory=list)
