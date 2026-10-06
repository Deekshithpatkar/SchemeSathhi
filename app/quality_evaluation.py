"""
Checkpoint 16: Quality and Accuracy Evaluation Module.
Quantitatively measures how well the extraction pipeline extracts genuine
individual candidate eligibility and exclusion rules from real Karnataka
government documents against a manually curated gold-standard benchmark.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class GoldRuleItem(BaseModel):
    """Ground truth representation of a genuine rule."""
    rule: str
    type: str = Field(description="'eligibility' or 'exclusion'")
    category: Optional[str] = None
    page_number: int
    evidence: str


class SchemeGoldStandard(BaseModel):
    """Gold standard annotation for a single scheme document."""
    scheme_key: str
    scheme_name: str
    document_filename: str
    has_rules: bool
    eligibility_rules: List[GoldRuleItem] = Field(default_factory=list)
    exclusion_rules: List[GoldRuleItem] = Field(default_factory=list)
    notes: str


class EvaluationMetrics(BaseModel):
    """Precision, Recall, F1 and confusion counts."""
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float


class DocumentQualityMetrics(BaseModel):
    """OCR and Document processing metrics."""
    total_pages: int
    digital_pages: int
    scanned_pages: int
    ocr_pages: int
    table_pages: int
    pages_requiring_ocr: int
    ocr_completed_successfully: int
    unusable_or_degraded_pages: int


class EvidenceQualityMetrics(BaseModel):
    """Grounding and evidence quality evaluation."""
    total_extracted_rules: int
    evidence_supported_count: int
    evidence_supported_pct: float
    incorrect_evidence_count: int
    incorrect_evidence_pct: float
    missing_evidence_count: int
    missing_evidence_pct: float
    rule_level_review_required_count: int
    rule_level_review_required_pct: float
    doc_level_review_required_count: int
    doc_level_review_required_pct: float


class Checkpoint16Evaluation(BaseModel):
    """Full CP16 evaluation artifact schema."""
    timestamp: str
    schemes_evaluated: int
    gold_standards: Dict[str, SchemeGoldStandard]
    eligibility_metrics: EvaluationMetrics
    exclusion_metrics: EvaluationMetrics
    combined_metrics: EvaluationMetrics
    document_processing: DocumentQualityMetrics
    evidence_quality: EvidenceQualityMetrics
    agent_evaluation: Dict[str, Any]
    knowledge_base_evaluation: Dict[str, Any]
    limitations: List[str]
    recommended_next_steps: List[str]
    conclusion: str


# ==============================================================================
# Gold Standard Annotations for Real Checkpoint 15 Documents
# ==============================================================================

GOLD_STANDARDS_5_SCHEMES: Dict[str, SchemeGoldStandard] = {
    "secondary-agriculture": SchemeGoldStandard(
        scheme_key="secondary-agriculture",
        scheme_name="Secondary Agriculture Directorate",
        document_filename="02a9ac3f_SecondaryAgriculturedirectorateGO.pdf",
        has_rules=False,
        eligibility_rules=[],
        exclusion_rules=[],
        notes="Official Government Order establishing the Directorate of Secondary Agriculture, defining committee structure and administrative composition. Contains no individual citizen/farmer eligibility or exclusion rules.",
    ),
    "gruha-lakshmi": SchemeGoldStandard(
        scheme_key="gruha-lakshmi",
        scheme_name="Gruha Lakshmi Scheme",
        document_filename="30af3c4d_GruhaLaxmiGO.pdf",
        has_rules=True,
        eligibility_rules=[
            GoldRuleItem(
                rule="Must be a woman recognized as head of the family (Yajamani) in Antyodaya, BPL, or APL ration cards issued by the Food and Civil Supplies Department",
                type="eligibility",
                category="gender_family_head",
                page_number=1,
                evidence="ಆಹಾರ ಮತ್ತು ನಾಗರಿಕ ಸರಬರಾಜು ಇಲಾಖೆಯು ವಿತರಿಸುವ ಅಂತ್ಯೋದಯ, ಬಿಪಿಎಲ್ ಮತ್ತು ಎಪಿಎಲ್ ಪಡಿತರ ಚೀಟಿಗಳಲ್ಲಿ ಕುಟುಂಬದ ಯಜಮಾನಿ ಎಂದು ನಮೂದಿಸಿರುವ ಮಹಿಳೆಗೆ",
            )
        ],
        exclusion_rules=[
            GoldRuleItem(
                rule="The woman head of household or her husband paying income tax or filing GST returns is excluded from the benefit",
                type="exclusion",
                category="taxpayer_exclusion",
                page_number=1,
                evidence="ಕುಟುಂಬದ ಯಜಮಾನಿ ಮಹಿಳೆ ಅಥವಾ ಆಕೆಯ ಪತಿ ಆದಾಯ ತೆರಿಗೆ ಅಥವಾ ಜಿಎಸ್‌ಟಿ ಪಾವತಿದಾರರಾಗಿದ್ದಲ್ಲಿ ಈ ಯೋಜನೆಯ ಸೌಲಭ್ಯಕ್ಕೆ ಅನರ್ಹರು",
            )
        ],
        notes="Official Government Order launching Gruha Lakshmi providing Rs. 2000/month to women family heads. Non-standard font encoding prevents clean Unicode text extraction in PDF parser.",
    ),
    "cm-raitha-vidyanidhi": SchemeGoldStandard(
        scheme_key="cm-raitha-vidyanidhi",
        scheme_name="Chief Minister Raitha Vidyanidhi Scholarship",
        document_filename="668bfe88_cmsclorship.pdf",
        has_rules=True,
        eligibility_rules=[
            GoldRuleItem(
                rule="Candidate must be a biological or legally adopted child of a farmer owning agricultural land in Karnataka, enrolled in an accredited post-matric course",
                type="eligibility",
                category="occupation_land_education",
                page_number=2,
                evidence="ರೈತ (Farmer), ಎಂದರೆ ರಾಜ್ಯದ ಯಾವುದೇ ಭಾಗದಲ್ಲಿ ಉಳುಮೆ ಮಾಡುವಂತಹ / ಕೃಷಿ ಮಾಡುವಂತಹ ಜಮೀನನ್ನು ತನ್ನ ಹೆಸರಿನಲ್ಲಿ ಹೊಂದಿರುವಂತಹ ವ್ಯಕ್ತಿ; ಮಕ್ಕಳು... ವಿದ್ಯಾಭ್ಯಾಸ",
            )
        ],
        exclusion_rules=[
            GoldRuleItem(
                rule="Students repeating an academic year or semester due to academic failure/re-examination are not eligible for scholarship continuation",
                type="exclusion",
                category="academic_failure_exclusion",
                page_number=3,
                evidence="ಕೋರ್ಸ್‌ನ ಸೆಮೆಸ್ಟರ್‌ನಲ್ಲಿ / ಶೈಕ್ಷಣಿಕ ವರ್ಷದಲ್ಲಿ ಅನುತ್ತೀರ್ಣ ಹೊಂದಿ ಪುನ: ಆ ಸೆಮಿಸ್ಟರ್‌ / ಶೈಕ್ಷಣಿಕ ವರ್ಷದಲ್ಲಿ ವಿದ್ಯಾಭ್ಯಾಸದ ಪುನರಾವರ್ತನೆಯಾದರೆ (ಪುನಃ ಪರೀಕ್ಷೆ ತೆಗೆದುಕೊಂಡರೆ) ವಿದ್ಯಾರ್ಥಿಗಳು ಶಿಷ್ಯವೇತನವನ್ನು ಪಡೆಯಲು ಅರ್ಹರಾಗಿರುವುದಿಲ್ಲ",
            ),
            GoldRuleItem(
                rule="Scholarship is limited to one degree course; students pursuing a second equivalent post-graduate degree after completing one are excluded",
                type="exclusion",
                category="duplicate_degree_exclusion",
                page_number=3,
                evidence="ಈ ಶಿಷ್ಯವೇತನವನ್ನು ಯಾವುದಾದರೂ ಒಂದು ವಿಧದ ಕೋರ್ಸ್‌ಗೆ ನೀಡಲಾಗುವುದು. ಉದಾಹರಣೆಗೆ, X ಎಂಬ ಸ್ನಾತಕೋತ್ತರ ಪದವಿಯನ್ನು ಪೂರೈಸಿದ ನಂತರ Y ಎಂಬ ಸ್ನಾತಕೋತ್ತರ ಕೋರ್ಸ್‌ಗೆ ವಿದ್ಯಾರ್ಥಿಯು ಪ್ರವೇಶ ಪಡೆದಲ್ಲಿ, ಈ ಕೋರ್ಸ್‌ಗೆ ಶಿಷ್ಯವೇತನವನ್ನು ಪಡೆಯಲು ಅರ್ಹವಾಗುವುದಿಲ್ಲ",
            ),
        ],
        notes="Purely scanned 4-page Kannada G.O. defining post-matric scholarship for farmers' children. Highly degraded OCR causes pipeline to miss all candidate rules.",
    ),
    "rkvy-karnataka": SchemeGoldStandard(
        scheme_key="rkvy-karnataka",
        scheme_name="Rashtriya Krishi Vikas Yojana (RKVY)",
        document_filename="1333e107_Allocation2021-22.pdf",
        has_rules=False,
        eligibility_rules=[],
        exclusion_rules=[],
        notes="Administrative Central Share funding allocation circular with state-wise funding table. Contains zero individual citizen eligibility conditions.",
    ),
    "pradhan-mantri-kisan-samman-nidhi": SchemeGoldStandard(
        scheme_key="pradhan-mantri-kisan-samman-nidhi",
        scheme_name="Pradhan Mantri Kisan Samman Nidhi (PM-KISAN)",
        document_filename="e116e94b_PMKISANKarnatakaGO.pdf",
        has_rules=False,
        eligibility_rules=[],
        exclusion_rules=[],
        notes="Karnataka State Government Order (13-08-2019) sanctioning state budgetary top-up release of Rs. 4,000 to existing PM-KISAN bank accounts via DBT. Contains no individual applicant qualification or exclusion criteria.",
    ),
}


def calculate_evaluation_metrics(
    true_positives: int, false_positives: int, false_negatives: int
) -> EvaluationMetrics:
    """Calculates precision, recall, and F1 score."""
    denom_p = true_positives + false_positives
    prec = (true_positives / denom_p) if denom_p > 0 else 0.0

    denom_r = true_positives + false_negatives
    rec = (true_positives / denom_r) if denom_r > 0 else 0.0

    denom_f1 = prec + rec
    f1 = (2 * prec * rec / denom_f1) if denom_f1 > 0 else 0.0

    return EvaluationMetrics(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=round(prec, 4),
        recall=round(rec, 4),
        f1_score=round(f1, 4),
    )
