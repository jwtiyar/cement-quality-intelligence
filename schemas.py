"""Pydantic request models for the API — strict, typed input validation."""

from __future__ import annotations

from typing import Any, Literal, Optional
from typing_extensions import Self

from pydantic import BaseModel, Field, model_validator


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
    SiO2: Optional[float] = Field(default=None, ge=0, le=100)
    Al2O3: Optional[float] = Field(default=None, ge=0, le=100)
    Fe2O3: Optional[float] = Field(default=None, ge=0, le=100)
    CaO: Optional[float] = Field(default=None, ge=0, le=100)
    MgO: Optional[float] = Field(default=None, ge=0, le=100)
    SO3: Optional[float] = Field(default=None, ge=0, le=100)
    Strength_Early: Optional[float] = Field(default=None, ge=0)
    Fineness: Optional[float] = Field(default=None, ge=0)


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
    # "calc" is the frontend's historical name for recipe mode
    mode: Literal["solve", "recipe", "calc"] = "solve"
    cement_type: Literal["OPC", "SRC", "SBC"] = "OPC"
    materials: dict[str, MaterialChemistry]
    targets: Optional[RawMixTargets] = None
    recipe: Optional[dict[str, float]] = None
    hfo: HFO = Field(default_factory=HFO)


class ChatTurn(BaseModel):
    role: Literal["user", "model"] = "user"
    content: str


class TypeSafePredictionReview(BaseModel):
    enabled: bool
    safe_to_show: Optional[bool] = None
    probability: Optional[float] = Field(default=None, ge=0, le=1)
    status: Literal["approved", "rejected", "not_reviewed"] = "not_reviewed"

    @model_validator(mode="before")
    @classmethod
    def normalize_status(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "status" not in data or data.get("status") is None:
                if not data.get("enabled"):
                    data["status"] = "not_reviewed"
                elif data.get("safe_to_show") is True:
                    data["status"] = "approved"
                elif data.get("safe_to_show") is False:
                    data["status"] = "rejected"
        return data

    @model_validator(mode="after")
    def validate_safety_consistency(self) -> Self:
        if self.status == "approved":
            if not self.enabled:
                raise ValueError("status 'approved' requires enabled=True")
            if self.safe_to_show is not True:
                raise ValueError("status 'approved' requires safe_to_show=True")
        elif self.status == "rejected":
            if not self.enabled:
                raise ValueError("status 'rejected' requires enabled=True")
            if self.safe_to_show is not False:
                raise ValueError("status 'rejected' requires safe_to_show=False")
        elif self.status == "not_reviewed":
            if self.enabled:
                raise ValueError("status 'not_reviewed' requires enabled=False")
            if self.safe_to_show is not None:
                raise ValueError("status 'not_reviewed' requires safe_to_show=None")
        return self


class PredictionContext(BaseModel):
    cement_type: Literal["OPC", "SRC", "SBC"]
    prediction: float
    prediction_source: Literal["xgboost", "recent_mean", "chemistry_only"]
    confidence: Literal["predictive", "exploratory", "chemistry_only", "insufficient_evidence"]
    confidence_label: str
    r2: Optional[float] = None
    rmse: Optional[float] = Field(default=None, ge=0)
    typesafe: TypeSafePredictionReview


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatTurn] = Field(default_factory=list)
    prediction_context: Optional[PredictionContext] = None
    provider: Literal["gemini", "codex"] = "gemini"
