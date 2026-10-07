"""
Checkpoint 17: Citizen Profile Schema.

Defines the structured Pydantic citizen profile for deterministic scheme eligibility evaluation.
Key Invariants:
1. Unknown != False (Optional fields default to None, meaning unknown/unspecified).
2. Missing values must never be coerced into 0, False, or arbitrary defaults.
3. Strongly typed with support for household structures and educational/agricultural attributes.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class HouseholdMember(BaseModel):
    """Represents an individual member within a citizen's household."""
    member_id: Optional[str] = None
    relationship: Optional[str] = None  # e.g., 'self', 'spouse', 'child', 'parent'
    gender: Optional[str] = None  # 'female', 'male', 'other'
    age: Optional[int] = None
    is_head: Optional[bool] = None
    already_received_benefit: Optional[bool] = None
    gst_registered: Optional[bool] = None
    income_tax_payer: Optional[bool] = None
    annual_income: Optional[float] = None
    owns_agricultural_land: Optional[bool] = None


class CitizenProfile(BaseModel):
    """
    Structured profile of a citizen seeking government scheme eligibility evaluation.
    All eligibility-relevant attributes default to None, signifying unknown information.
    """
    citizen_id: Optional[str] = None
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None  # 'female', 'male', 'other'
    state: Optional[str] = None  # e.g., 'Karnataka'
    district: Optional[str] = None
    residency_status: Optional[str] = None  # 'resident', 'non_resident'
    is_karnataka_resident: Optional[bool] = None

    # Employment & Government Service
    occupation: Optional[str] = None
    employment_status: Optional[str] = None  # 'employed', 'unemployed', 'self_employed', 'student'
    government_employee: Optional[bool] = None

    # Financial & Income
    income: Optional[float] = None  # Monthly or unspecified income
    annual_income: Optional[float] = None  # Normalized annual family/personal income in INR
    income_tax_payer: Optional[bool] = None
    gst_registered: Optional[bool] = None
    gst_return_filer: Optional[bool] = None

    # Land & Agriculture
    landholding_acres: Optional[float] = None
    owns_agricultural_land: Optional[bool] = None
    farmer: Optional[bool] = None
    farmer_category: Optional[str] = None  # 'small', 'marginal', 'large'

    # Social & Demographics
    caste_category: Optional[str] = None  # 'SC', 'ST', 'OBC', 'General'
    marital_status: Optional[str] = None
    disability_status: Optional[bool] = None
    disability_percentage: Optional[float] = None

    # Household & Family
    household_id: Optional[str] = None
    household_members: Optional[List[HouseholdMember]] = None
    household_head: Optional[bool] = None
    is_woman_head_of_household: Optional[bool] = None
    ration_card_type: Optional[str] = None  # 'BPL', 'APL', 'Antyodaya', 'AAY'
    listed_as_head_in_ration_card: Optional[bool] = None
    spouse_is_gst_filer: Optional[bool] = None
    spouse_is_taxpayer: Optional[bool] = None

    # Education & Academic Standing
    education_level: Optional[str] = None  # 'undergraduate', 'postgraduate', 'sslc', 'puc'
    current_course: Optional[str] = None
    previous_course: Optional[str] = None
    failed_semester: Optional[bool] = None
    repeating_year: Optional[bool] = None
    already_completed_equivalent_or_higher_course: Optional[bool] = None

    # Scheme Benefits History
    beneficiary_already_received: Optional[bool] = None
    prior_benefits: Optional[List[str]] = Field(default_factory=list)

    # Freeform extensible attributes
    attributes: Dict[str, Any] = Field(default_factory=dict)

    def get_effective_annual_income(self) -> Optional[float]:
        """Returns annual_income, or annualizes monthly income if available."""
        if self.annual_income is not None:
            return float(self.annual_income)
        if self.income is not None:
            # If specified as <= 50,000 assume monthly and annualize
            if self.income <= 50000:
                return float(self.income * 12)
            return float(self.income)
        return None

    def has_household_info(self) -> bool:
        """Checks if structured household member details are populated."""
        return self.household_members is not None and len(self.household_members) > 0


def normalize_citizen_input(
    raw_text: str,
    base_profile: Optional[CitizenProfile] = None,
    llm_client: Optional[Any] = None,
) -> CitizenProfile:
    """
    Normalizes natural language citizen input into structured CitizenProfile fields.
    Validates all extracted values with deterministic Python logic before applying.
    """
    import re
    profile = base_profile.model_copy() if base_profile else CitizenProfile()
    text_lower = raw_text.lower()

    # 1. Monthly income phrases (e.g. '20k a month', 'earn 20000 monthly', '20,000 per month')
    monthly_k_match = re.search(r"(\d+(?:\.\d+)?)\s*k\s*(?:a\s*month|per\s*month|monthly)", text_lower)
    if monthly_k_match:
        monthly_val = float(monthly_k_match.group(1)) * 1000.0
        profile.income = monthly_val
        profile.annual_income = monthly_val * 12.0

    monthly_raw_match = re.search(r"(?:earn|salary|income\s*is)?\s*(?:rs\.?|₹)?\s*(\d{4,6})\s*(?:a\s*month|per\s*month|monthly)", text_lower)
    if monthly_raw_match:
        monthly_val = float(monthly_raw_match.group(1))
        profile.income = monthly_val
        profile.annual_income = monthly_val * 12.0

    # 2. Annual income phrases (e.g. '2.5 lakh per year', 'annual income 300000')
    annual_lakh_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac)\s*(?:per\s*year|annually|annual|a\s*year)?", text_lower)
    if annual_lakh_match and not monthly_k_match:
        annual_val = float(annual_lakh_match.group(1)) * 100000.0
        profile.annual_income = annual_val

    # 3. Gender & Family Status
    if any(w in text_lower for w in ["woman", "female", "ಮಹಿಳೆ"]):
        profile.gender = "female"
    elif any(w in text_lower for w in ["man", "male", "ಪುರುಷ"]):
        profile.gender = "male"

    if any(w in text_lower for w in ["head of family", "household head", "woman head", "ಯಜಮಾನಿ"]):
        profile.household_head = True
        if profile.gender == "female":
            profile.is_woman_head_of_household = True

    # 4. Ration Card
    for card in ["bpl", "apl", "antyodaya", "aay"]:
        if card in text_lower:
            profile.ration_card_type = card.upper()
            break
    if "head in ration card" in text_lower or "listed as head" in text_lower or "ration card head" in text_lower:
        profile.listed_as_head_in_ration_card = True

    # 5. Landholding
    land_match = re.search(r"(\d+(?:\.\d+)?)\s*acres?", text_lower)
    if land_match:
        acres = float(land_match.group(1))
        profile.landholding_acres = acres
        profile.owns_agricultural_land = acres > 0.0
    elif "landless" in text_lower or "no land" in text_lower:
        profile.owns_agricultural_land = False
        profile.landholding_acres = 0.0

    # 6. Academic Standing
    if "failed" in text_lower or "fail" in text_lower:
        profile.failed_semester = True
    elif "passed" in text_lower:
        profile.failed_semester = False

    if "repeating" in text_lower or "repeat" in text_lower:
        profile.repeating_year = True

    # 7. Tax / GST
    if "gst registered" in text_lower or "gst return" in text_lower:
        profile.gst_return_filer = True
    if "taxpayer" in text_lower or "income tax payer" in text_lower:
        profile.income_tax_payer = True

    # 8. State / Residency
    if "karnataka" in text_lower:
        profile.state = "Karnataka"
        profile.is_karnataka_resident = True

    return profile
