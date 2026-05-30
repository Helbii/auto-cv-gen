"""
Shim de compatibilité — re-exporte tout depuis les trois modules spécialisés.
Importer directement depuis matching, audit ou markdown est préférable pour
le nouveau code, mais tous les importeurs existants continuent de fonctionner.

DEPRECATED : ce module sera supprimé dans une future version.
Migrer les imports vers .matching, .audit ou .markdown directement.
"""
import warnings
warnings.warn(
    "services.generator est déprécié — importez directement depuis "
    ".matching, .audit ou .markdown selon le symbole souhaité.",
    DeprecationWarning,
    stacklevel=2,
)
# Re-exports intentionnels — les hints "not accessed" sont attendus dans un shim.
from .matching import (  # noqa: F401
    find_candidate_evidence_for_requirement,
    build_requirement_groups,
    compute_matching_score,
    compute_matching_score_details,
    extract_offer_title,
    build_dynamic_title,
    extract_safe_context_terms,
    extract_offer_sector,
    enrich_matching_with_offer_context,
    compact_requirements,
    extract_requirements_from_offer,
    is_transferable_requirement,
    split_requirement_parts,
    is_valid_requirement,
    infer_recommended_title,
    classify_requirement,
    build_fallback_matching,
    enrich_matching_with_extracted_requirements,
    normalize_matching_requirements,
    adjust_for_training_context,
    apply_cross_requirement_reasoning,
    enrich_matching_with_implicit_requirements,
    candidate_total_years,
    candidate_max_education,
    complete_matching_safety_fields,
    allowed_evidence_from_matching,
)

from .audit import (  # noqa: F401
    contains_forbidden_claim,
    contains_unsupported_claim,
    validate_generated_cv,
    build_safe_summary,
    resolve_safe_title,
    resolve_safe_summary,
    resolve_safe_email,
)

from .markdown import (  # noqa: F401
    extract_static_cv_sections,
    group_experience_bullets,
    build_skill_experience_map,
    annotate_audit_skills,
    stack_for_source,
    generate_database_recruiter_markdown,
    generate_recruiter_markdown,
    generate_email_markdown,
    generate_audit_markdown,
    generate_markdown,
    save_outputs,
)
