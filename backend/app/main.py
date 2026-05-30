import json
import logging
import re
from fastapi import FastAPI, HTTPException, Query

logger = logging.getLogger(__name__)
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .schemas import JobRequest, UploadCVRequest, UpdatePdfRequest
from .services.evidence import build_evidence_bank, evidence_by_id
from .services.storage import index_evidence, load_all_evidence, has_index
from .services.retrieval import retrieve_relevant_evidence
from .services.ollama_client import call_ollama_json, iter_ollama_stream, parse_streaming_result, OllamaError
from .services.generator import (
    compute_matching_score,
    compute_matching_score_details,
    build_fallback_matching,
    build_requirement_groups,
    enrich_matching_with_extracted_requirements,
    normalize_matching_requirements,
    adjust_for_training_context,
    apply_cross_requirement_reasoning,
    enrich_matching_with_implicit_requirements,
    enrich_matching_with_offer_context,
    complete_matching_safety_fields,
    allowed_evidence_from_matching,
    validate_generated_cv,
    annotate_audit_skills,
    generate_markdown,
    generate_audit_markdown,
    generate_email_markdown,
    save_outputs,
)
from .services.rendercv_export import build_rendercv_yaml_data, export_rendercv_files, render_rendercv_data
from .services.docx_export import generate_cv_docx
from .services.history import (
    init_history_db, make_history_folder, save_generation,
    list_generations, get_generation, delete_generation, read_generation_files,
)
from .prompts import (
    MATCHING_SCHEMA,
    GENERATED_CV_SCHEMA,
    build_matching_prompt,
    build_generation_prompt,
)


app = FastAPI(title="Auto CV Gen", version="0.1.0")
init_history_db(settings.history_db_path)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_cv_master() -> dict:
    if not settings.cv_path.exists():
        raise FileNotFoundError(f"CV introuvable : {settings.cv_path}")
    return json.loads(settings.cv_path.read_text(encoding="utf-8"))


@app.get("/health")
def health():
    return {
        "status": "ok",
        "matching_model": settings.matching_model,
        "generation_model": settings.generation_model,
        "ollama_base_url": settings.ollama_base_url,
        "cv_path": str(settings.cv_path),
        "sqlite_path": str(settings.sqlite_path),
        "has_index": has_index(settings.sqlite_path),
    }


@app.post("/api/upload-cv")
def upload_cv(payload: UploadCVRequest):
    settings.cv_path.parent.mkdir(parents=True, exist_ok=True)
    settings.cv_path.write_text(json.dumps(payload.cv_master, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "saved", "path": str(settings.cv_path)}


@app.post("/api/index-cv")
def index_cv():
    try:
        cv_master = load_cv_master()
        evidence_bank = build_evidence_bank(cv_master)
        index_evidence(settings.sqlite_path, evidence_bank)
        evidence_path = settings.output_dir / "evidence_bank.json"
        evidence_path.write_text(json.dumps(evidence_bank, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "status": "indexed",
            "count": len(evidence_bank),
            "evidence_file": str(evidence_path),
        }
    except Exception as exc:
        logger.exception("Erreur lors de l'indexation du CV")
        raise HTTPException(status_code=500, detail="Erreur lors de l'indexation. Vérifiez les logs.")


@app.get("/api/evidence")
def get_evidence():
    if not has_index(settings.sqlite_path):
        raise HTTPException(status_code=400, detail="Index absent. Lance /api/index-cv d'abord.")
    return {"items": load_all_evidence(settings.sqlite_path)}


@app.post("/api/retrieve")
def retrieve(payload: JobRequest):
    if not has_index(settings.sqlite_path):
        raise HTTPException(status_code=400, detail="Index absent. Lance /api/index-cv d'abord.")
    top_k = payload.top_k or settings.top_k
    evidence = retrieve_relevant_evidence(settings.sqlite_path, payload.job_offer, top_k=top_k)
    return {"count": len(evidence), "items": evidence}


@app.post("/api/generate-cv")
def generate_cv(payload: JobRequest):
    if not has_index(settings.sqlite_path):
        # Auto-index si possible
        index_cv()

    matching_model = payload.matching_model or settings.matching_model
    generation_model = payload.generation_model or payload.model or settings.generation_model
    top_k = min(payload.top_k or settings.top_k, settings.max_evidence_for_llm)

    try:
        cv_master = load_cv_master()
        evidence_bank = retrieve_relevant_evidence(settings.sqlite_path, payload.job_offer, top_k=top_k)
        all_indexed_evidence = load_all_evidence(settings.sqlite_path)
        id_to_evidence = evidence_by_id(all_indexed_evidence)

        req_groups = build_requirement_groups(payload.job_offer, evidence_bank)
        matching_prompt = build_matching_prompt(
            payload.job_offer, evidence_bank,
            all_evidence=all_indexed_evidence,
            requirement_groups=req_groups,
        )
        matching = call_ollama_json(
            base_url=settings.ollama_base_url,
            model=matching_model,
            prompt=matching_prompt,
            format_schema=MATCHING_SCHEMA,
            required_keys=[
                "recommended_title",
                "matching_score",
                "job_keywords",
                "requirements_analysis",
                "confirmed_skill_evidence_ids",
                "transferable_skill_evidence_ids",
                "forbidden_claims",
            ],
            temperature=0.05,
            timeout=1200,
        )

        if not matching.get("requirements_analysis"):
            matching = build_fallback_matching(payload.job_offer, evidence_bank)

        matching = enrich_matching_with_extracted_requirements(matching, payload.job_offer, evidence_bank)
        matching = normalize_matching_requirements(matching, all_indexed_evidence, trust_llm_evidence=True)
        matching = adjust_for_training_context(matching, payload.job_offer)
        matching = apply_cross_requirement_reasoning(matching)
        matching = enrich_matching_with_implicit_requirements(matching, payload.job_offer, cv_master)
        matching = enrich_matching_with_offer_context(matching, payload.job_offer)
        matching = complete_matching_safety_fields(matching)
        score_breakdown = compute_matching_score_details(matching)
        matching["matching_score"] = score_breakdown["score"]
        matching["score_breakdown"] = score_breakdown
        allowed_evidence = allowed_evidence_from_matching(matching, all_indexed_evidence)

        if not allowed_evidence:
            allowed_evidence = evidence_bank[: min(10, len(evidence_bank))]

        forbidden_claims = matching.get("forbidden_claims", [])

        generation_prompt = build_generation_prompt(payload.job_offer, matching, allowed_evidence, forbidden_claims, all_evidence=all_indexed_evidence)
        generated = call_ollama_json(
            base_url=settings.ollama_base_url,
            model=generation_model,
            prompt=generation_prompt,
            format_schema=GENERATED_CV_SCHEMA,
            required_keys=["targeted_cv"],
            temperature=0.1,
            timeout=1200,
        )

        if not isinstance(generated.get("targeted_cv"), dict):
            raise OllamaError("Ollama a renvoyé targeted_cv invalide (attendu: dict, reçu: {}).".format(type(generated.get("targeted_cv")).__name__))
        generated["targeted_cv"]["matching_score"] = matching["matching_score"]
        allowed_ids = {ev["id"] for ev in allowed_evidence}
        audit = validate_generated_cv(generated, allowed_ids, forbidden_claims)
        audit = annotate_audit_skills(audit, cv_master)
        final_md = generate_markdown(matching, generated, audit, id_to_evidence, cv_master)
        audit_md = generate_audit_markdown(matching, generated, audit, id_to_evidence)
        email_md = generate_email_markdown(matching, generated, audit)
        rendercv_data = build_rendercv_yaml_data(matching, generated, audit, id_to_evidence, cv_master=cv_master, options=payload.pdf_design)
        if payload.custom_title:
            rendercv_data.setdefault("cv", {})["headline"] = payload.custom_title
        rendercv_files = render_rendercv_data(settings.output_dir, rendercv_data)

        output_files = save_outputs(settings.output_dir, {
            "retrieved_evidence.json": evidence_bank,
            "matching_analysis.json": matching,
            "allowed_evidence.json": allowed_evidence,
            "generated_cv.json": generated,
            "audit_report.json": audit,
            "cv_recruiter.md": final_md,
            "email.md": email_md,
            "audit_report.md": audit_md,
        })
        output_files.update(rendercv_files)

        return {
            "matching": matching,
            "generated_cv": generated,
            "audit": audit,
            "final_markdown": final_md,
            "email_markdown": email_md,
            "audit_markdown": audit_md,
            "editable_cv": rendercv_data.get("cv", {}),
            "pdf_design": payload.pdf_design or {"font_size": 9.25, "margin": "normal"},
            "output_files": output_files,
        }

    except OllamaError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("Erreur inattendue lors de la génération CV")
        raise HTTPException(status_code=500, detail="Erreur interne lors de la génération. Vérifiez les logs.")


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _assess_generation_quality(generated: dict) -> list:
    """Détecte une génération pauvre. Retourne la liste des problèmes (vide si OK)."""
    cv = generated.get("targeted_cv", {})
    if not isinstance(cv, dict):
        return ["Structure targeted_cv invalide"]
    bullets = cv.get("experience_bullets", []) or []
    skills = cv.get("skills_to_display", []) or []
    summary = cv.get("professional_summary", "") or ""

    issues = []
    if len(bullets) < 4:
        issues.append(f"Seulement {len(bullets)} bullets d'expérience (5 à 8 attendus)")
    if len(skills) < 4:
        issues.append(f"Seulement {len(skills)} compétences affichées (6 à 9 attendues)")
    if len(summary.strip()) < 80:
        issues.append("Résumé professionnel trop court (viser 3 phrases)")
    short_bullets = sum(1 for b in bullets if len(str(b.get("bullet", "")).strip()) < 40)
    if short_bullets >= 2:
        issues.append(f"{short_bullets} bullets trop courts ou génériques")
    return issues


@app.post("/api/generate-cv/stream")
def generate_cv_stream(payload: JobRequest):
    def event_generator():
        try:
            if not has_index(settings.sqlite_path):
                yield _sse({"step": "auto_index", "message": "Indexation automatique du CV..."})
                _cv = load_cv_master()
                index_evidence(settings.sqlite_path, build_evidence_bank(_cv))

            matching_model = payload.matching_model or settings.matching_model
            generation_model = payload.generation_model or payload.model or settings.generation_model
            top_k = min(payload.top_k or settings.top_k, settings.max_evidence_for_llm)

            yield _sse({"step": "retrieval", "message": "Récupération des preuves..."})
            cv_master = load_cv_master()
            evidence_bank = retrieve_relevant_evidence(settings.sqlite_path, payload.job_offer, top_k=top_k)
            all_indexed_evidence = load_all_evidence(settings.sqlite_path)
            id_to_evidence = evidence_by_id(all_indexed_evidence)
            yield _sse({"step": "retrieval_done", "message": f"{len(evidence_bank)} preuves récupérées", "count": len(evidence_bank)})

            yield _sse({"step": "matching", "message": "Analyse de matching avec l'offre..."})
            req_groups = build_requirement_groups(payload.job_offer, evidence_bank)
            matching_prompt = build_matching_prompt(
                payload.job_offer, evidence_bank,
                all_evidence=all_indexed_evidence,
                requirement_groups=req_groups,
            )
            matching_raw = ""
            matching_tokens = 0
            for _token, _done in iter_ollama_stream(
                base_url=settings.ollama_base_url,
                model=matching_model,
                prompt=matching_prompt,
                format_schema=MATCHING_SCHEMA,
                temperature=0.05,
                timeout=1200,
            ):
                matching_raw += _token
                matching_tokens += 1
                if matching_tokens % 30 == 0:
                    yield _sse({"step": "llm_token", "phase": "matching", "count": matching_tokens})
            yield _sse({"step": "llm_token", "phase": "matching", "count": matching_tokens})
            try:
                matching = parse_streaming_result(matching_raw, required_keys=[
                    "recommended_title", "matching_score", "job_keywords",
                    "requirements_analysis", "confirmed_skill_evidence_ids",
                    "transferable_skill_evidence_ids", "forbidden_claims",
                ])
            except OllamaError as exc:
                raise OllamaError(
                    "Matching LLM invalide : CV non genere pour eviter une analyse fallback moins fine. "
                    f"Detail : {exc}"
                ) from exc

            if not matching.get("requirements_analysis"):
                matching = build_fallback_matching(payload.job_offer, evidence_bank)

            matching = enrich_matching_with_extracted_requirements(matching, payload.job_offer, evidence_bank)
            matching = normalize_matching_requirements(matching, all_indexed_evidence, trust_llm_evidence=True)
            matching = adjust_for_training_context(matching, payload.job_offer)
            matching = apply_cross_requirement_reasoning(matching)
            matching = enrich_matching_with_implicit_requirements(matching, payload.job_offer, cv_master)
            matching = enrich_matching_with_offer_context(matching, payload.job_offer)
            matching = complete_matching_safety_fields(matching)
            score_breakdown = compute_matching_score_details(matching)
            matching["matching_score"] = score_breakdown["score"]
            matching["score_breakdown"] = score_breakdown
            allowed_evidence = allowed_evidence_from_matching(matching, all_indexed_evidence)
            if not allowed_evidence:
                allowed_evidence = evidence_bank[:min(10, len(evidence_bank))]

            yield _sse({
                "step": "matching_done",
                "message": "Matching terminé",
                "score": matching["matching_score"],
                "requirements": len(matching.get("requirements_analysis", [])),
                "confirmed": len(matching.get("confirmed_skill_evidence_ids", [])),
            })

            forbidden_claims = matching.get("forbidden_claims", [])

            def _stream_generation(retry_issues=None):
                """Génère via streaming, yield les events token, retourne le dict parsé."""
                prompt = build_generation_prompt(
                    payload.job_offer, matching, allowed_evidence, forbidden_claims,
                    all_evidence=all_indexed_evidence, retry_issues=retry_issues,
                )
                raw = ""
                count = 0
                for _token, _done in iter_ollama_stream(
                    base_url=settings.ollama_base_url,
                    model=generation_model,
                    prompt=prompt,
                    format_schema=GENERATED_CV_SCHEMA,
                    temperature=0.1 if not retry_issues else 0.2,
                    timeout=1200,
                ):
                    raw += _token
                    count += 1
                    if count % 30 == 0:
                        yield _sse({"step": "llm_token", "phase": "generating", "count": count})
                yield _sse({"step": "llm_token", "phase": "generating", "count": count})
                parsed = parse_streaming_result(raw, required_keys=["targeted_cv"])
                if not isinstance(parsed.get("targeted_cv"), dict):
                    raise OllamaError(
                        "Ollama a renvoyé targeted_cv invalide (attendu: dict, reçu: {}).".format(
                            type(parsed.get("targeted_cv")).__name__))
                return parsed

            yield _sse({"step": "generating", "message": "Génération du CV ciblé..."})
            generated = yield from _stream_generation()

            # Détection de génération pauvre → un seul retry ciblé
            quality_issues = _assess_generation_quality(generated)
            if quality_issues:
                yield _sse({
                    "step": "generating_retry",
                    "message": "Génération insuffisante, nouvelle tentative...",
                    "issues": quality_issues,
                })
                retried = yield from _stream_generation(retry_issues=quality_issues)
                # On garde la meilleure des deux (plus de bullets+skills)
                def _richness(g):
                    cv = g.get("targeted_cv", {})
                    return len(cv.get("experience_bullets", []) or []) + len(cv.get("skills_to_display", []) or [])
                if _richness(retried) >= _richness(generated):
                    generated = retried

            generated["targeted_cv"]["matching_score"] = matching["matching_score"]
            yield _sse({"step": "generating_done", "message": "Génération terminée"})

            yield _sse({"step": "auditing", "message": "Audit anti-hallucination..."})
            allowed_ids = {ev["id"] for ev in allowed_evidence}
            audit = validate_generated_cv(generated, allowed_ids, forbidden_claims)
            audit = annotate_audit_skills(audit, cv_master)
            final_md = generate_markdown(matching, generated, audit, id_to_evidence, cv_master)
            audit_md = generate_audit_markdown(matching, generated, audit, id_to_evidence)
            email_md = generate_email_markdown(matching, generated, audit)
            yield _sse({
                "step": "audit_done",
                "message": "Audit terminé",
                "valid_bullets": len(audit.get("valid_bullets", [])),
                "rejected_bullets": len(audit.get("rejected_bullets", [])),
                "valid_skills": len(audit.get("valid_skills", [])),
            })

            yield _sse({"step": "rendering", "message": "Génération PDF & DOCX..."})
            rendercv_data = build_rendercv_yaml_data(matching, generated, audit, id_to_evidence, cv_master=cv_master, options=payload.pdf_design)
            if payload.custom_title:
                rendercv_data.setdefault("cv", {})["headline"] = payload.custom_title
            rendercv_files = render_rendercv_data(settings.output_dir, rendercv_data)

            docx_path = settings.output_dir / "cv_targeted.docx"
            try:
                generate_cv_docx(matching, generated, audit, id_to_evidence, cv_master, docx_path)
                rendercv_files["cv_targeted.docx"] = str(docx_path)
            except Exception as exc:
                logger.warning("DOCX non généré (non bloquant) : %s", exc)

            output_files = save_outputs(settings.output_dir, {
                "retrieved_evidence.json": evidence_bank,
                "matching_analysis.json": matching,
                "allowed_evidence.json": allowed_evidence,
                "generated_cv.json": generated,
                "audit_report.json": audit,
                "cv_recruiter.md": final_md,
                "email.md": email_md,
                "audit_report.md": audit_md,
            })
            output_files.update(rendercv_files)

            # Sauvegarde dans l'historique
            title = payload.custom_title or matching.get("safe_recommended_title") or matching.get("recommended_title", "CV cible")
            history_dir = settings.output_dir / "history"
            history_folder = make_history_folder(history_dir, title)
            editable_cv = rendercv_data.get("cv", {})
            save_outputs(history_folder, {
                "matching_analysis.json": matching,
                "generated_cv.json": generated,
                "audit_report.json": audit,
                "cv_recruiter.md": final_md,
                "email.md": email_md,
                "audit_report.md": audit_md,
                "editable_cv.json": editable_cv,
                "pdf_design.json": payload.pdf_design or {"font_size": 9.25, "margin": "normal"},
            })
            pdf_src = settings.output_dir / "cv_targeted.pdf"
            if pdf_src.exists():
                import shutil as _shutil
                _shutil.copy2(pdf_src, history_folder / "cv_targeted.pdf")
            save_generation(
                db_path=settings.history_db_path,
                folder=history_folder,
                title=title,
                score=matching.get("matching_score", 0),
                job_offer=payload.job_offer,
                valid_bullets=len(audit.get("valid_bullets", [])),
                valid_skills=len(audit.get("valid_skills", [])),
                model=f"{matching_model} → {generation_model}",
                offer_url=payload.offer_url,
            )

            yield _sse({
                "step": "complete",
                "data": {
                    "matching": matching,
                    "generated_cv": generated,
                    "audit": audit,
                    "final_markdown": final_md,
                    "email_markdown": email_md,
                    "audit_markdown": audit_md,
                    "editable_cv": editable_cv,
                    "pdf_design": payload.pdf_design or {"font_size": 9.25, "margin": "normal"},
                    "output_files": output_files,
                },
            })

        except OllamaError as exc:
            yield _sse({"step": "error", "message": str(exc), "status": 502})
        except Exception as exc:
            yield _sse({"step": "error", "message": str(exc), "status": 500})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/update-pdf")
def update_pdf(payload: UpdatePdfRequest):
    try:
        data = {
            "cv": payload.cv,
            "design": build_design(payload.pdf_design),
            "locale": {
                "language": "french",
                "last_updated": "Dernière mise à jour",
                "present": "présent",
            },
        }
        headline = str(payload.cv.get("headline") or "cv_targeted")
        output_files = render_rendercv_data(settings.output_dir, data, base_name=sanitize_pdf_filename(headline).removesuffix(".pdf"))
        return {
            "status": "updated",
            "editable_cv": payload.cv,
            "pdf_design": payload.pdf_design or {"font_size": 9.25, "margin": "normal"},
            "output_files": output_files,
        }
    except Exception as exc:
        logger.exception("Erreur lors de la mise à jour du PDF")
        raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour du PDF. Vérifiez les logs.")


@app.get("/api/history")
def get_history():
    init_history_db(settings.history_db_path)
    return {"items": list_generations(settings.history_db_path)}


@app.get("/api/history/{gen_id}")
def get_history_entry(gen_id: int):
    entry = get_generation(settings.history_db_path, gen_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entrée introuvable.")
    from pathlib import Path as _Path
    files = read_generation_files(_Path(entry["folder"]))
    return {**entry, **files}


@app.delete("/api/history/{gen_id}")
def delete_history_entry(gen_id: int):
    result = delete_generation(settings.history_db_path, gen_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Entrée introuvable.")
    return {"status": "deleted", "folder": result}


@app.get("/api/history/{gen_id}/pdf")
def download_history_pdf(gen_id: int, filename: str | None = Query(default=None, max_length=120)):
    entry = get_generation(settings.history_db_path, gen_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entrée introuvable.")
    from pathlib import Path as _Path
    pdf = _Path(entry["folder"]) / "cv_targeted.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail="PDF absent pour cette entrée.")
    if filename:
        safe_title = sanitize_pdf_filename(filename)
        return FileResponse(path=str(pdf), media_type="application/pdf", filename=safe_title)
    return FileResponse(path=str(pdf), media_type="application/pdf")


def sanitize_pdf_filename(value: str | None) -> str:
    filename = str(value or "").strip()
    if not filename:
        return "cv_targeted.pdf"
    filename = re.sub(r"[^\w\s.\-()]", "_", filename, flags=re.UNICODE)
    filename = re.sub(r"\s+", "_", filename).strip("._- ")
    if not filename:
        filename = "cv_targeted"
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"
    return filename[:120]


@app.get("/api/download/pdf")
def download_pdf(filename: str | None = Query(default=None, max_length=120)):
    pdf_path = settings.output_dir / "cv_targeted.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF absent. Genere d'abord un CV.")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=sanitize_pdf_filename(filename),
    )


@app.get("/api/download/docx")
def download_docx(filename: str | None = Query(default=None, max_length=120)):
    docx_path = settings.output_dir / "cv_targeted.docx"
    if not docx_path.exists():
        raise HTTPException(status_code=404, detail="DOCX absent. Génère d'abord un CV.")
    safe_name = sanitize_pdf_filename(filename).replace(".pdf", ".docx")
    return FileResponse(
        path=str(docx_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=safe_name,
    )


@app.get("/api/preview/pdf")
def preview_pdf():
    pdf_path = settings.output_dir / "cv_targeted.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF absent. Genere d'abord un CV.")
    return FileResponse(path=str(pdf_path), media_type="application/pdf")
