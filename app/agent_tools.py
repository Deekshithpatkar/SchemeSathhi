"""
Agent Tools and Central Tool Registry for Checkpoint 14.
Exposes the existing verified components from CP1–CP13 as callable, safe tools.

Invariants:
1. No raw Python/shell code execution.
2. Tools handle actual work; the agent orchestrates.
3. Full CP9 OCR/table pipeline is preserved.
4. Input validation and structured error reporting on all tools.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Union

from app.config import setup_logger
from app.registry import get_sources as registry_get_sources
from app.document_discovery import discover_documents_from_page
from app.downloader import download_file
from app.document_processor import process_document_understanding
from app.rule_extractor import extract_scheme_rules
from app.comparison import compare_documents as run_doc_comparison
from app.rule_comparison import compare_rules as run_rule_comparison
from app.knowledge_base import (
    apply_knowledge_update,
    get_current_rules as kb_get_current_rules,
    get_historical_versions as kb_get_historical_versions,
)

logger = setup_logger("agent_tools")


# ==============================================================================
# Tool Implementations
# ==============================================================================

def tool_discover_sources(
    scheme_name: Optional[str] = None,
    department: Optional[str] = None,
    active_only: bool = True,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Returns trusted configured Karnataka government sources from the registry.
    Prevents the agent from scanning arbitrary untrusted websites.
    """
    try:
        sources = registry_get_sources(active_only=active_only)
        clean_sources = [
            {
                "id": s["id"],
                "source_name": s["source_name"],
                "official_url": s["official_url"],
                "department": s.get("department"),
                "source_type": s.get("source_type"),
            }
            for s in sources
        ]

        # Prioritize or filter matching sources if specific scheme or department queried
        if department:
            dept_lower = department.lower()
            matching = [s for s in clean_sources if s.get("department") and dept_lower in s["department"].lower()]
            if matching:
                clean_sources = matching
        elif scheme_name:
            sn_lower = scheme_name.lower().replace("-", " ")
            if any(k in sn_lower for k in ["kisan", "pm-kisan", "raitha", "farmer", "agriculture"]):
                matching = [s for s in clean_sources if "agri" in (s.get("department") or "").lower() or "raitha" in (s.get("source_name") or "").lower()]
                if matching:
                    clean_sources = matching
            elif any(k in sn_lower for k in ["lakshmi", "wcd", "women"]):
                matching = [s for s in clean_sources if "wcd" in (s.get("department") or "").lower() or "lakshmi" in (s.get("source_name") or "").lower()]
                if matching:
                    clean_sources = matching
            elif any(k in sn_lower for k in ["jyothi", "energy", "bescom"]):
                matching = [s for s in clean_sources if "energy" in (s.get("department") or "").lower() or "jyothi" in (s.get("source_name") or "").lower()]
                if matching:
                    clean_sources = matching
            elif any(k in sn_lower for k in ["bhagya", "ahara", "food", "ration"]):
                matching = [s for s in clean_sources if "food" in (s.get("department") or "").lower() or "ahara" in (s.get("source_name") or "").lower()]
                if matching:
                    clean_sources = matching

        return {
            "status": "success",
            "sources_count": len(clean_sources),
            "sources": clean_sources,
        }
    except Exception as e:
        logger.error(f"tool_discover_sources failed: {e}")
        return {"status": "failed", "error": str(e), "sources": []}


def tool_discover_documents(
    source_url: str = "",
    scheme_name: Optional[str] = None,
    department: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Discovers relevant scheme documents (guidelines, government orders, notifications)
    on an official Karnataka government webpage, or handles a direct document URL.
    """
    try:
        if not source_url:
            return {"status": "failed", "error": "source_url is required"}

        # If source_url is already a direct PDF URL
        if source_url.lower().endswith(".pdf"):
            doc_name = source_url.split("/")[-1]
            return {
                "status": "success",
                "documents_count": 1,
                "documents": [{
                    "document_url": source_url,
                    "title": doc_name,
                    "document_type": "order" if any(k in doc_name.lower() for k in ["go", "order"]) else "guideline",
                    "source_page_url": source_url,
                    "published_date": None,
                    "is_scheme_document": True,
                }],
            }

        docs = discover_documents_from_page(
            page_url=source_url,
            scheme_name=scheme_name,
            department=department,
            scheme_only=True,
        )
        return {
            "status": "success",
            "documents_count": len(docs),
            "documents": docs,
        }
    except Exception as e:
        logger.error(f"tool_discover_documents failed for {source_url}: {e}")
        return {"status": "failed", "error": str(e), "documents": []}


def tool_download_document(document_url: str = "", **kwargs: Any) -> Dict[str, Any]:
    """
    Downloads a document from an official URL, calculates its SHA-256 fingerprint,
    verifies PDF format, and saves it locally.
    """
    try:
        if not document_url:
            return {"status": "failed", "error": "document_url is required"}

        meta = download_file(url=document_url)
        if not meta:
            return {
                "status": "failed",
                "error": f"Failed to download document from {document_url}",
            }

        return {
            "status": "success",
            "file_path": meta["file_path"],
            "file_name": meta["file_name"],
            "file_hash": meta["file_hash"],
            "file_size": meta["file_size"],
            "is_pdf": meta["is_pdf"],
        }
    except Exception as e:
        logger.error(f"tool_download_document failed for {document_url}: {e}")
        return {"status": "failed", "error": str(e)}


def tool_process_document(
    file_path: str = "",
    source_url: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Runs the comprehensive document understanding pipeline (PyMuPDF digital text,
    Tesseract spatial OCR, Kannada language models, table & layout analysis).
    Generates structured Step 9 JSON.
    """
    try:
        if not file_path:
            return {"status": "failed", "error": "file_path is required"}

        p = Path(file_path)
        if not p.exists():
            return {"status": "failed", "error": f"File does not exist: {file_path}"}

        doc_info = process_document_understanding(
            file_path=p,
            languages="kan+eng",
            dpi=300,
            source_url=source_url,
        )

        return {
            "status": "success",
            "file_name": doc_info["file_name"],
            "total_pages": doc_info["total_pages"],
            "usable_pages_count": doc_info["usable_pages_count"],
            "scanned_pages_count": doc_info["scanned_pages_count"],
            "ocr_performed": doc_info["ocr_performed"],
            "tables_detected_count": doc_info["tables_detected_count"],
            "structured_json_path": doc_info["structured_json_path"],
            "full_text_preview": (doc_info["full_text"][:300] + "...") if doc_info.get("full_text") else "",
        }
    except Exception as e:
        logger.error(f"tool_process_document failed for {file_path}: {e}")
        return {"status": "failed", "error": str(e)}


def tool_extract_eligibility_rules(
    structured_json_path: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Runs CP10 semantic extraction on the structured document JSON.
    Extracts candidate eligibility rules and exclusion rules with grounded physical evidence.
    """
    try:
        if not structured_json_path:
            return {"status": "failed", "error": "structured_json_path is required"}

        p = Path(structured_json_path)
        if not p.exists():
            return {"status": "failed", "error": f"Structured JSON not found: {structured_json_path}"}

        extraction = extract_scheme_rules(doc_input=p)
        ext_dict = extraction.model_dump(mode="json")

        return {
            "status": "success",
            "scheme_name": ext_dict.get("scheme_name"),
            "department": ext_dict.get("department"),
            "eligibility_rules_count": len(ext_dict.get("eligibility_rules", [])),
            "exclusion_rules_count": len(ext_dict.get("exclusion_rules", [])),
            "review_required": ext_dict.get("review_required", False),
            "review_reasons": ext_dict.get("review_reasons", []),
            "extraction_data": ext_dict,
        }
    except Exception as e:
        logger.error(f"tool_extract_eligibility_rules failed for {structured_json_path}: {e}")
        return {"status": "failed", "error": str(e)}


def tool_compare_documents(
    old_doc: Any = None,
    new_doc: Any = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Runs CP11 document comparison to determine if document text changed and
    whether the change is potentially eligibility-relevant.
    """
    try:
        if old_doc is None or new_doc is None:
            return {"status": "failed", "error": "Both old_doc and new_doc are required"}

        comp = run_doc_comparison(old_doc=old_doc, new_doc=new_doc, save_output=False)
        comp_dict = comp.model_dump(mode="json")
        return {
            "status": "success",
            "hash_status": comp_dict.get("hash_status"),
            "overall_status": comp_dict.get("overall_status"),
            "eligibility_relevance": comp_dict.get("eligibility_relevance"),
            "review_required": comp_dict.get("review_required"),
            "semantic_summary": comp_dict.get("semantic_summary"),
            "comparison_data": comp_dict,
        }
    except Exception as e:
        logger.error(f"tool_compare_documents failed: {e}")
        return {"status": "failed", "error": str(e)}


def tool_compare_rules(
    old_rules: Any = None,
    new_rules: Any = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Runs CP12 rule comparison to evaluate specific candidate qualification changes,
    directional impact, and review flags.
    """
    try:
        if old_rules is None or new_rules is None:
            return {"status": "failed", "error": "Both old_rules and new_rules are required"}

        comp_res = run_rule_comparison(
            old_rules_input=old_rules,
            new_rules_input=new_rules,
            save_output=False,
        )
        res_dict = comp_res.model_dump(mode="json")
        return {
            "status": "success",
            "eligibility_relevance": res_dict.get("eligibility_relevance"),
            "summary": res_dict.get("summary"),
            "added_rules_count": len(res_dict.get("added_rules", [])),
            "removed_rules_count": len(res_dict.get("removed_rules", [])),
            "modified_rules_count": len(res_dict.get("modified_rules", [])),
            "unchanged_rules_count": len(res_dict.get("unchanged_rules", [])),
            "review_required": res_dict.get("review_required", False),
            "review_reasons": res_dict.get("review_reasons", []),
            "comparison_data": res_dict,
        }
    except Exception as e:
        logger.error(f"tool_compare_rules failed: {e}")
        return {"status": "failed", "error": str(e)}


def tool_update_knowledge_base(
    scheme_key: str = "",
    scheme_name: str = "",
    document_hash: str = "",
    version_label: str = "",
    department: Optional[str] = None,
    document_date: Optional[str] = None,
    source_url: Optional[str] = None,
    rules_extraction: Optional[Dict[str, Any]] = None,
    comparison_result: Optional[Dict[str, Any]] = None,
    force_review: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Runs CP13 transactional PostgreSQL persistence.
    Archives previous active version, creates new ACTIVE or REVIEW version,
    persists candidate rules with physical evidence, and records audit update logs.
    """
    try:
        if not scheme_key or not scheme_name or not document_hash:
            return {
                "status": "failed",
                "error": "scheme_key, scheme_name, and document_hash are required",
            }

        res = apply_knowledge_update(
            scheme_key=scheme_key,
            scheme_name=scheme_name,
            document_hash=document_hash,
            version_label=version_label or "v1",
            department=department,
            document_date=document_date,
            source_url=source_url,
            rules_extraction=rules_extraction,
            comparison_result=comparison_result,
            force_review=force_review,
        )
        return {
            "status": "success",
            "kb_status": res["status"],
            "version_id": res.get("version_id"),
            "version_status": res.get("version_status"),
            "action_taken": res.get("action_taken"),
            "rules_stored": res.get("rules_stored", 0),
            "review_required": res.get("review_required", False),
            "message": res.get("message", ""),
        }
    except Exception as e:
        logger.error(f"tool_update_knowledge_base failed: {e}")
        return {"status": "failed", "error": str(e)}


def tool_get_current_rules(
    scheme_key: str = "",
    scheme_name: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Queries the PostgreSQL knowledge base for currently active candidate eligibility
    and exclusion rules for a specific Karnataka scheme.
    """
    try:
        target_key = scheme_key or scheme_name or ""
        if not target_key:
            return {"status": "failed", "error": "scheme_key is required"}

        rules_info = kb_get_current_rules(scheme_key=target_key)
        if not rules_info:
            return {"status": "not_found", "message": f"Scheme '{target_key}' not found"}

        return {
            "status": "success",
            "scheme_key": rules_info["scheme_key"],
            "scheme_name": rules_info["scheme_name"],
            "active_version": rules_info["active_version"]["version_label"] if rules_info.get("active_version") else None,
            "document_hash": rules_info["active_version"]["document_hash"] if rules_info.get("active_version") else None,
            "eligibility_rules_count": len(rules_info.get("eligibility_rules", [])),
            "exclusion_rules_count": len(rules_info.get("exclusion_rules", [])),
            "eligibility_rules": rules_info.get("eligibility_rules", []),
            "exclusion_rules": rules_info.get("exclusion_rules", []),
        }
    except Exception as e:
        logger.error(f"tool_get_current_rules failed for {scheme_key}: {e}")
        return {"status": "failed", "error": str(e)}


def tool_get_historical_versions(
    scheme_key: str = "",
    scheme_name: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Queries all historical versions of a Karnataka scheme from the PostgreSQL knowledge base.
    """
    try:
        target_key = scheme_key or scheme_name or ""
        if not target_key:
            return {"status": "failed", "error": "scheme_key is required"}

        versions = kb_get_historical_versions(scheme_key=target_key)
        clean_versions = [
            {
                "id": v["id"],
                "version_label": v["version_label"],
                "document_hash": v.get("document_hash"),
                "status": v["status"],
                "document_date": str(v.get("document_date")) if v.get("document_date") else None,
                "created_at": str(v.get("created_at")) if v.get("created_at") else None,
            }
            for v in versions
        ]
        return {
            "status": "success",
            "scheme_key": target_key,
            "versions_count": len(clean_versions),
            "versions": clean_versions,
        }
    except Exception as e:
        logger.error(f"tool_get_historical_versions failed for {scheme_key}: {e}")
        return {"status": "failed", "error": str(e)}


# ==============================================================================
# Central Tool Registry
# ==============================================================================

TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "discover_sources": {
        "function": tool_discover_sources,
        "description": "Returns trusted, configured Karnataka government scheme sources from the source registry.",
        "parameters": {
            "active_only": "bool: If True (default), returns only active sources."
        },
    },
    "discover_documents": {
        "function": tool_discover_documents,
        "description": "Scrapes and discovers official scheme documents (guidelines, government orders, notifications) from a trusted source portal.",
        "parameters": {
            "source_url": "str (required): The official website or portal URL to check for scheme documents.",
            "scheme_name": "str (optional): The name of the target scheme.",
            "department": "str (optional): The government department name.",
        },
    },
    "download_document": {
        "function": tool_download_document,
        "description": "Downloads a scheme document PDF, calculates its SHA-256 hash fingerprint, and saves it locally.",
        "parameters": {
            "document_url": "str (required): The URL of the document PDF to download."
        },
    },
    "process_document": {
        "function": tool_process_document,
        "description": "Executes full document understanding (digital text extraction, Kannada OCR, OpenCV table detection, layout coordinates) to produce structured Step 9 JSON.",
        "parameters": {
            "file_path": "str (required): Local file path to the downloaded PDF.",
            "source_url": "str (optional): The original URL where the document was discovered.",
        },
    },
    "extract_eligibility_rules": {
        "function": tool_extract_eligibility_rules,
        "description": "Extracts candidate eligibility and exclusion rules with grounded physical evidence from the structured document JSON.",
        "parameters": {
            "structured_json_path": "str (required): Path to the Step 9 structured document JSON file."
        },
    },
    "compare_documents": {
        "function": tool_compare_documents,
        "description": "Compares an old and new document version to assess document-level changes and eligibility relevance.",
        "parameters": {
            "old_doc": "str or dict (required): Path or dictionary of the old document representation.",
            "new_doc": "str or dict (required): Path or dictionary of the new document representation.",
        },
    },
    "compare_rules": {
        "function": tool_compare_rules,
        "description": "Compares extracted candidate eligibility and exclusion rule sets to detect added, removed, or modified criteria and their direction of impact.",
        "parameters": {
            "old_rules": "str or dict (required): Path or dictionary of old extracted rules.",
            "new_rules": "str or dict (required): Path or dictionary of new extracted rules.",
        },
    },
    "update_knowledge_base": {
        "function": tool_update_knowledge_base,
        "description": "Atomically persists the validated scheme version and its eligibility rules to the PostgreSQL knowledge base, preserving history.",
        "parameters": {
            "scheme_key": "str (required): Stable scheme identifier (e.g. 'karnataka_pm_kisan').",
            "scheme_name": "str (required): Official scheme name.",
            "document_hash": "str (required): SHA-256 hash of the document.",
            "version_label": "str (required): Human-readable version label (e.g. '2024-v1').",
            "department": "str (optional): Department name.",
            "document_date": "str (optional): Publication date of document in YYYY-MM-DD format.",
            "source_url": "str (optional): Official source URL.",
            "rules_extraction": "dict (optional): CP10 extracted rules data.",
            "comparison_result": "dict (optional): CP12 rule comparison result.",
            "force_review": "bool (optional): If True, stores version as REVIEW without activating.",
        },
    },
    "get_current_rules": {
        "function": tool_get_current_rules,
        "description": "Queries the active eligibility and exclusion rules for a Karnataka scheme from the PostgreSQL knowledge base.",
        "parameters": {
            "scheme_key": "str (required): Stable scheme identifier."
        },
    },
    "get_historical_versions": {
        "function": tool_get_historical_versions,
        "description": "Retrieves the historical timeline of all archived and active versions for a scheme from the PostgreSQL knowledge base.",
        "parameters": {
            "scheme_key": "str (required): Stable scheme identifier."
        },
    },
}


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Central dispatcher executing only registered tools with argument validation.
    Prevents any arbitrary execution of code.
    """
    if tool_name not in TOOL_REGISTRY:
        return {
            "status": "failed",
            "error": f"Tool '{tool_name}' is not a registered tool. Available tools: {list(TOOL_REGISTRY.keys())}",
            "review_required": True,
        }

    tool_entry = TOOL_REGISTRY[tool_name]
    func = tool_entry["function"]

    try:
        result = func(**arguments)
        return result
    except TypeError as te:
        return {
            "status": "failed",
            "error": f"Invalid arguments passed to tool '{tool_name}': {te}",
            "review_required": True,
        }
    except Exception as e:
        logger.error(f"Error during execution of tool '{tool_name}': {e}")
        return {
            "status": "failed",
            "error": f"Execution error in tool '{tool_name}': {str(e)}",
            "review_required": True,
        }
