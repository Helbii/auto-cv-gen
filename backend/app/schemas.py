from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    id: str
    category: str
    source: str
    field: str
    text: str


class JobRequest(BaseModel):
    job_offer: str = Field(..., min_length=20)
    top_k: Optional[int] = None
    model: Optional[str] = None              # rétrocompat : mappé sur generation_model si fourni seul
    matching_model: Optional[str] = None
    generation_model: Optional[str] = None
    pdf_design: Optional[Dict[str, Any]] = None
    offer_url: Optional[str] = Field(default=None, max_length=500)


class UpdatePdfRequest(BaseModel):
    cv: Dict[str, Any]
    pdf_design: Optional[Dict[str, Any]] = None


class UploadCVRequest(BaseModel):
    cv_master: Dict[str, Any]


class GenerateResponse(BaseModel):
    matching: Dict[str, Any]
    generated_cv: Dict[str, Any]
    audit: Dict[str, Any]
    final_markdown: str
    output_files: Dict[str, str]
