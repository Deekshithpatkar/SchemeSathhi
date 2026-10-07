"""
Checkpoint 17: Scheme Evaluation API Interface.

Exposes endpoints for citizen eligibility evaluation.
Designed to be compatible with FastAPI if available, while remaining
independently importable and callable without FastAPI installed.
"""

from typing import Dict, Any, List, Optional
from app.citizen_profile import CitizenProfile
from app.eligibility_schemas import EligibilityResult
from app.eligibility_engine import evaluate_citizen, evaluate_citizen_against_schemes


def evaluate_scheme_endpoint(
    scheme_key: str,
    profile: CitizenProfile,
    version_label: Optional[str] = None,
) -> EligibilityResult:
    """
    Core handler for POST /schemes/{scheme_key}/evaluate.
    Accepts CitizenProfile and returns EligibilityResult.
    """
    return evaluate_citizen(profile, scheme_key=scheme_key, version_label=version_label)


def evaluate_multiple_schemes_endpoint(
    scheme_keys: List[str],
    profile: CitizenProfile,
) -> Dict[str, EligibilityResult]:
    """
    Core handler for POST /schemes/evaluate-multiple.
    Accepts list of scheme keys and CitizenProfile.
    """
    return evaluate_citizen_against_schemes(profile, scheme_keys=scheme_keys)


# Conditional FastAPI Router setup if fastapi package is installed in environment
try:
    from fastapi import APIRouter, HTTPException, Query

    router = APIRouter(prefix="/schemes", tags=["Citizen Eligibility Evaluation"])

    @router.post("/{scheme_key}/evaluate", response_model=EligibilityResult)
    def api_evaluate_scheme(
        scheme_key: str,
        profile: CitizenProfile,
        version_label: Optional[str] = Query(None, description="Optional historical version label to evaluate"),
    ) -> EligibilityResult:
        try:
            return evaluate_scheme_endpoint(scheme_key, profile, version_label=version_label)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/evaluate-multiple", response_model=Dict[str, EligibilityResult])
    def api_evaluate_multiple(
        scheme_keys: List[str],
        profile: CitizenProfile,
    ) -> Dict[str, EligibilityResult]:
        try:
            return evaluate_multiple_schemes_endpoint(scheme_keys, profile)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

except ImportError:
    router = None
