import React, { useState, useRef, useEffect } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const PIPELINE_STEPS = [
  { id: "retrieval", label: "Récupération des preuves" },
  { id: "matching",  label: "Analyse de matching" },
  { id: "generating", label: "Génération du CV" },
  { id: "auditing",  label: "Audit anti-hallucination" },
  { id: "rendering", label: "Export PDF" },
];

const DEFAULT_PDF_DESIGN = {
  theme: "engineeringclassic",
  preset: "classic",
  font_size: 9.25,
  margin: "normal",
  primary_color: "blue",
  section_spacing: 0.20,
  entry_spacing: 0.58,
  bullet_spacing: 0.045,
  show_icons: true,
  underline_links: false,
  show_footer: false,
};

const MODEL_PRESETS = [
  { value: "balanced", label: "Équilibré — 8b matching / 14b génération", matching: "qwen3:8b",  generation: "qwen3:14b" },
  { value: "fast",     label: "Rapide    — 8b / 8b",                        matching: "qwen3:8b",  generation: "qwen3:8b"  },
  { value: "quality",  label: "Qualité   — 14b / 30b",                      matching: "qwen3:14b", generation: "qwen3:30b" },
];

const SECTION_LABELS = ["Résumé", "Compétences clés", "Expérience", "Projets", "Formation", "Langues"];

function StepDot({ status }) {
  return <div className={`step-dot s-${status}`} />;
}

function App() {
  const [customTitle, setCustomTitle] = useState("");
  const [jobOffer, setJobOffer]       = useState("");
  const [offerUrl, setOfferUrl]       = useState("");
  const [modelPreset, setModelPreset]  = useState("balanced");
  const [topK, setTopK]               = useState(45);
  const [loading, setLoading]         = useState(false);
  const [status, setStatus]           = useState("");
  const [error, setError]             = useState("");
  const [result, setResult]           = useState(null);
  const [outputMode, setOutputMode]   = useState("cv");
  const [pdfFilename, setPdfFilename] = useState("BEN_ROKIA_Bilel_CV");
  const [editableCv, setEditableCv]   = useState(null);
  const [pdfDesign, setPdfDesign]     = useState(DEFAULT_PDF_DESIGN);
  const [pdfKey, setPdfKey]           = useState(Date.now());
  const [steps, setSteps]             = useState(null);
  const [cvFilename, setCvFilename]   = useState("");
  const fileInputRef                  = useRef(null);
  const abortControllerRef            = useRef(null);
  const [history, setHistory]         = useState([]);
  const [activeHistoryId, setActiveHistoryId] = useState(null);
  const [editedMarkdown, setEditedMarkdown]   = useState({});
  const [hiddenSections, setHiddenSections]   = useState({});

  useEffect(() => { fetchHistory(); }, []);

  async function fetchHistory() {
    try {
      const res = await fetch("/api/history");
      if (res.ok) { const d = await res.json(); setHistory(d.items || []); }
    } catch {}
  }

  async function loadHistoryEntry(id) {
    setLoading(true); setError(""); setStatus("Chargement de l'historique...");
    try {
      const res = await fetch(`/api/history/${id}`);
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || "Erreur chargement");
      setResult(d);
      setEditableCv(d.editable_cv || null);
      setPdfDesign({ ...DEFAULT_PDF_DESIGN, ...(d.pdf_design || {}) });
      setActiveHistoryId(id); setEditedMarkdown({});
      setHiddenSections({});
      setPdfKey(Date.now());
      setOutputMode("cv");
      setSteps(PIPELINE_STEPS.map(s => ({ ...s, status: "done", detail: null })));
      setStatus("");
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }

  async function deleteHistoryEntry(id) {
    try {
      const res = await fetch(`/api/history/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Suppression échouée côté serveur.");
      setHistory(prev => prev.filter(e => e.id !== id));
    } catch (e) { setError(e.message); }
  }

  const freshSteps = () => PIPELINE_STEPS.map(s => ({ ...s, status: "pending", detail: null }));

  function setStep(id, status, detail = null) {
    setSteps(prev => prev.map(s => s.id === id ? { ...s, status, detail } : s));
  }

  async function indexCv() {
    setLoading(true); setError(""); setStatus("Indexation du CV...");
    try {
      const res = await fetch("/api/index-cv", { method: "POST" });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || "Erreur indexation");
      setStatus(`CV indexé — ${d.count} preuves extraites`);
    } catch (e) { setError(e.message); setStatus(""); }
    finally { setLoading(false); }
  }

  async function uploadCv(file) {
    setLoading(true); setError(""); setStatus("Lecture du fichier...");
    try {
      const text = await file.text();
      let cvMaster;
      try { cvMaster = JSON.parse(text); }
      catch { throw new Error("Fichier JSON invalide — vérifie la syntaxe."); }

      setStatus("Upload du CV...");
      const res = await fetch("/api/upload-cv", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cv_master: cvMaster }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || "Erreur upload");

      setStatus("Indexation en cours...");
      const res2 = await fetch("/api/index-cv", { method: "POST" });
      const d2 = await res2.json();
      if (!res2.ok) throw new Error(d2.detail || "Erreur indexation");

      setCvFilename(file.name);
      setStatus(`CV chargé et indexé — ${d2.count} preuves extraites`);
    } catch (e) { setError(e.message); setStatus(""); }
    finally { setLoading(false); }
  }

  async function generateCv() {
    if (!jobOffer.trim()) { setError("Colle d'abord une offre d'emploi."); return; }

    const preset = MODEL_PRESETS.find(x => x.value === modelPreset);
    if (!preset) { setError("Preset modèle inconnu."); return; }

    const payload = {
      job_offer: jobOffer,
      matching_model: preset.matching,
      generation_model: preset.generation,
      top_k: Number(topK),
      offer_url: offerUrl.trim() || null,
      pdf_design: pdfDesign,
      custom_title: customTitle.trim() || null,
    };

    if (abortControllerRef.current) abortControllerRef.current.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;
    const timeoutId = setTimeout(() => controller.abort(), 300_000);

    setLoading(true); setError(""); setResult(null); setEditableCv(null); setStatus("");
    setActiveHistoryId(null); setEditedMarkdown({});
    setHiddenSections({});
    setOutputMode("cv"); setSteps(freshSteps());

    try {
      const res = await fetch("/api/generate-cv/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail || "Erreur génération");
      }

      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          let ev;
          try { ev = JSON.parse(line.slice(6)); } catch { continue; }

          switch (ev.step) {
            case "auto_index":     setStatus(ev.message); break;
            case "retrieval":      setStep("retrieval", "running"); break;
            case "retrieval_done": setStep("retrieval", "done", `${ev.count} preuves`); break;
            case "matching":       setStep("matching",  "running"); break;
            case "matching_done":  setStep("matching",  "done", `Score ${ev.score}/100 · ${ev.requirements} exigences`); break;
            case "generating":     setStep("generating","running"); break;
            case "generating_retry": setStep("generating","running", "Reprise — génération enrichie"); break;
            case "generating_done":setStep("generating","done"); break;
            case "llm_token":
              setSteps(prev => prev?.map(s =>
                s.id === ev.phase && s.status === "running"
                  ? { ...s, detail: `${ev.count.toLocaleString()} tokens` }
                  : s
              ));
              break;
            case "auditing":       setStep("auditing",  "running"); break;
            case "audit_done":     setStep("auditing",  "done", `${ev.valid_bullets} bullets · ${ev.valid_skills} compétences`); break;
            case "rendering":      setStep("rendering", "running"); break;
            case "complete":
              setStep("rendering", "done");
              setResult(ev.data);
              const ecv = ev.data.editable_cv || null;
              if (ecv && customTitle.trim()) ecv.headline = customTitle.trim();
              setEditableCv(ecv);
              setPdfDesign({ ...DEFAULT_PDF_DESIGN, ...(ev.data.pdf_design || {}) });
              setActiveHistoryId(null);
              setHiddenSections({});
              setPdfKey(Date.now());
              setStatus("");
              fetchHistory();
              break;
            case "error":
              setError(ev.message);
              setSteps(prev => prev.map(s => s.status === "running" ? { ...s, status: "error" } : s));
              break;
          }
        }
      }
    } catch (e) {
      if (e.name === "AbortError") {
        setError("Génération annulée ou délai dépassé (5 min).");
      } else {
        setError(e.message);
      }
      setSteps(prev => prev?.map(s => s.status === "running" ? { ...s, status: "error" } : s));
    } finally {
      clearTimeout(timeoutId);
      setLoading(false);
    }
  }

  function downloadPdf() {
    const f = encodeURIComponent(pdfFilename.trim() || "cv_targeted");
    const url = activeHistoryId
      ? `/api/history/${activeHistoryId}/pdf?filename=${f}`
      : `/api/download/pdf?filename=${f}`;
    window.open(url, "_blank", "noopener,noreferrer");
  }

  async function updatePdf() {
    if (!editableCv) return;
    setLoading(true); setError(""); setStatus("Mise à jour du PDF...");
    try {
      const res = await fetch("/api/update-pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cv: editableCv, pdf_design: pdfDesign }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || "Erreur mise à jour PDF");
      const nextDesign = { ...DEFAULT_PDF_DESIGN, ...(d.pdf_design || {}) };
      setPdfDesign(nextDesign);
      setResult(cur => ({ ...cur, editable_cv: d.editable_cv, pdf_design: nextDesign, output_files: { ...(cur?.output_files || {}), ...(d.output_files || {}) } }));
      setActiveHistoryId(null);
      setPdfKey(Date.now());
      setStatus("PDF mis à jour.");
    } catch (e) { setError(e.message); setStatus(""); }
    finally { setLoading(false); }
  }

  function patchCv(patch) {
    setEditableCv(cv => ({ ...(cv || {}), ...patch }));
  }
  function patchSection(name, value) {
    setEditableCv(cv => ({ ...(cv || {}), sections: { ...((cv || {}).sections || {}), [name]: value } }));
  }
  function patchExp(index, patch) {
    const exps = [...(editableCv?.sections?.["Expérience"] || [])];
    exps[index] = { ...exps[index], ...patch };
    patchSection("Expérience", exps);
  }
  function patchSkill(index, patch) {
    const skills = [...(editableCv?.sections?.["Compétences clés"] || [])];
    skills[index] = { ...skills[index], ...patch };
    patchSection("Compétences clés", skills);
  }
  function addSkill() {
    patchSection("Compétences clés", [...(editableCv?.sections?.["Compétences clés"] || []), { label: "Nouvelle compétence", details: "" }]);
  }
  function removeSkill(index) {
    patchSection("Compétences clés", (editableCv?.sections?.["Compétences clés"] || []).filter((_, i) => i !== index));
  }
  function patchBullet(expIndex, bulletIndex, value) {
    const exps = [...(editableCv?.sections?.["Expérience"] || [])];
    const highlights = [...(exps[expIndex]?.highlights || [])];
    highlights[bulletIndex] = value;
    exps[expIndex] = { ...exps[expIndex], highlights };
    patchSection("Expérience", exps);
  }
  function addBullet(expIndex) {
    const exps = [...(editableCv?.sections?.["Expérience"] || [])];
    const highlights = [...(exps[expIndex]?.highlights || []), "Nouveau bullet à adapter"];
    exps[expIndex] = { ...exps[expIndex], highlights };
    patchSection("Expérience", exps);
  }
  function removeBullet(expIndex, bulletIndex) {
    const exps = [...(editableCv?.sections?.["Expérience"] || [])];
    const highlights = (exps[expIndex]?.highlights || []).filter((_, i) => i !== bulletIndex);
    exps[expIndex] = { ...exps[expIndex], highlights };
    patchSection("Expérience", exps);
  }
  function moveExperience(index, direction) {
    const exps = [...(editableCv?.sections?.["Expérience"] || [])];
    const target = index + direction;
    if (target < 0 || target >= exps.length) return;
    [exps[index], exps[target]] = [exps[target], exps[index]];
    patchSection("Expérience", exps);
  }
  function toggleSection(name) {
    const current = editableCv?.sections?.[name];
    if (current) {
      setHiddenSections(prev => ({ ...prev, [name]: current }));
      setEditableCv(cv => {
        const sections = { ...((cv || {}).sections || {}) };
        delete sections[name];
        return { ...(cv || {}), sections };
      });
    } else {
      const restored = hiddenSections[name] || (name === "Résumé" ? [""] : []);
      patchSection(name, restored);
      setHiddenSections(prev => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
    }
  }
  function applyDesignPreset(mode) {
    const presets = {
      fill:    { preset: "airy",    font_size: 9.75, margin: "large",   section_spacing: 0.26, entry_spacing: 0.72, bullet_spacing: 0.06 },
      compact: { preset: "compact", font_size: 8.75, margin: "compact", section_spacing: 0.16, entry_spacing: 0.46, bullet_spacing: 0.035 },
      tech:    { preset: "tech",    font_size: 9.15, margin: "normal",  section_spacing: 0.18, entry_spacing: 0.52, bullet_spacing: 0.04 },
    };
    setPdfDesign(design => ({ ...design, ...(presets[mode] || {}) }));
  }

  const audit = result?.audit;
  const scoreBreakdown = result?.matching?.score_breakdown;
  const originalMarkdown = outputMode === "cv" ? result?.final_markdown : result?.audit_markdown;
  // Texte édité par mode (null = utilise l'original du résultat)
  const markdown = editedMarkdown[outputMode] ?? originalMarkdown ?? "";

  function setMarkdownForMode(value) {
    setEditedMarkdown(prev => ({ ...prev, [outputMode]: value }));
  }

  function copyMarkdown() {
    navigator.clipboard?.writeText(markdown).then(
      () => { setStatus("Copié dans le presse-papier."); setTimeout(() => setStatus(""), 2000); },
      () => setError("Copie impossible.")
    );
  }

  function downloadMarkdown() {
    const names = { cv: "cv_recruteur", audit: "audit" };
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(pdfFilename.trim() || "cv")}_${names[outputMode] || outputMode}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    /* ── NEW LAYOUT ─────────────────────────────────────────────────────── */
    <div className="app-layout">

      {/* ════════════ SIDEBAR ════════════ */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon">CV</div>
          <div>
            <div className="brand-name">AutoCV</div>
            <div className="brand-sub">Générateur intelligent</div>
          </div>
        </div>

        <div className="sidebar-scroll">

          {/* CV source */}
          <div className="sidebar-section">
            <div className="sidebar-section-title">CV source</div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              style={{ display: "none" }}
              onChange={e => { if (e.target.files[0]) uploadCv(e.target.files[0]); e.target.value = ""; }}
            />
            <div className="btn-stack">
              <button className="btn btn-pri btn-full" onClick={() => fileInputRef.current.click()} disabled={loading}>
                ↑ Charger CV JSON
              </button>
              <button className="btn btn-ghost btn-sm btn-full" onClick={indexCv} disabled={loading}>
                Re-indexer
              </button>
            </div>
            {cvFilename
              ? <p className="cv-loaded">✓ {cvFilename}</p>
              : <p className="hint">Charge ton <code>cv_master.json</code></p>
            }
          </div>

          {/* Modèle */}
          <div className="sidebar-section">
            <div className="sidebar-section-title">Modèle</div>
            <select className="sel" value={modelPreset} onChange={e => setModelPreset(e.target.value)}>
              {MODEL_PRESETS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
            <label className="field" style={{ marginTop: 10 }}>
              <span className="flabel">Preuves envoyées au LLM</span>
              <input className="inp" type="number" min="10" max="60" value={topK} onChange={e => setTopK(e.target.value)} />
            </label>
          </div>

          {/* Pipeline */}
          {steps && (
            <div className="sidebar-section">
              <div className="sidebar-section-title">
                Pipeline
                {result && <span className="badge badge-ok">Terminé</span>}
              </div>
              <div className="pipeline">
                {steps.map(s => (
                  <div key={s.id} className={`pstep s-${s.status}`}>
                    <StepDot status={s.status} />
                    <div className="pstep-body">
                      <span className="pstep-label">{s.label}</span>
                      {s.detail && <span className="pstep-detail">{s.detail}</span>}
                    </div>
                    <div className="pstep-icon">
                      {s.status === "running" && <span className="spin" />}
                      {s.status === "done"    && <span className="ico-ok">✓</span>}
                      {s.status === "error"   && <span className="ico-err">✕</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Historique */}
          {history.length > 0 && (
            <div className="sidebar-section">
              <div className="sidebar-section-title">
                Historique
                <span className="hist-count">{history.length}</span>
              </div>
              <div className="hist-list">
                {history.map(entry => (
                  <div key={entry.id} className="hist-item">
                    <div className="hist-item-header">
                      <span className="hist-title">{entry.title || "—"}</span>
                      <span className="hstat hstat-score">{entry.score ?? "—"}</span>
                    </div>
                    <div className="hist-meta">
                      {entry.created_at?.replace("T", " ").slice(0, 16)}
                    </div>
                    <div className="hist-item-actions">
                      <button className="btn btn-sec btn-sm" onClick={() => loadHistoryEntry(entry.id)} disabled={loading}>CV</button>
                      <a className="btn btn-ghost btn-sm" href={`/api/history/${entry.id}/pdf?filename=${encodeURIComponent(entry.title || "cv")}`} target="_blank" rel="noopener noreferrer">PDF</a>
                      {entry.offer_url && (
                        <a className="btn btn-ghost btn-sm" href={entry.offer_url} target="_blank" rel="noopener noreferrer" title={entry.offer_url}>Offre ↗</a>
                      )}
                      <button className="btn btn-icon" onClick={() => deleteHistoryEntry(entry.id)} title="Supprimer">✕</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      </aside>

      {/* ════════════ MAIN ════════════ */}
      <main className="main-zone">
        <div className="main-inner">

          {/* Feedback */}
          {status && <div className="bar bar-info">{status}</div>}
          {error  && <div className="bar bar-err">{error}</div>}

          {/* Offre */}
          <div>
            <div className="offer-header">
              <h1 className="offer-title">Générer un CV ciblé</h1>
              <p className="offer-sub">Colle le texte d'une offre pour créer un CV optimisé ATS en quelques minutes.</p>
            </div>
            <div className="offer-inputs">
              <div className="cv-title-bar">
                <label className="cv-title-label">Emploi ciblé</label>
                <input
                  className="inp cv-title-input"
                  placeholder="ex : Ingénieur Python – IA Générative"
                  value={customTitle}
                  onChange={e => setCustomTitle(e.target.value)}
                />
              </div>
              <textarea
                className="inp textarea offer-ta"
                placeholder="Colle ici l'offre complète…"
                value={jobOffer}
                onChange={e => setJobOffer(e.target.value)}
              />
              <div className="offer-footer">
                <input
                  className="inp offer-url"
                  type="url"
                  placeholder="Lien de l'offre (optionnel)"
                  value={offerUrl}
                  onChange={e => setOfferUrl(e.target.value)}
                />
                <button className="btn btn-pri btn-lg" onClick={generateCv} disabled={loading}>
                  {loading ? <><span className="btn-spin" />Génération…</> : "Générer →"}
                </button>
              </div>
            </div>
          </div>

          {/* ── Résultats ── */}
          {result && (
            <>

              {/* Score banner */}
              {audit && (
                <div className="score-banner">
                  <div className="score-main">
                    <span className="score-number">{result.matching?.matching_score ?? 0}</span>
                    <span className="score-label">/100 ATS</span>
                  </div>
                  <div className="score-stats">
                    <div className="sstat">
                      <span className="sstat-val green">{audit.valid_bullets?.length ?? 0}</span>
                      <span className="sstat-lbl">bullets</span>
                    </div>
                    <div className="sstat">
                      <span className="sstat-val blue">{audit.valid_skills?.length ?? 0}</span>
                      <span className="sstat-lbl">skills</span>
                    </div>
                    <div className="sstat">
                      <span className="sstat-val red">{audit.rejected_bullets?.length ?? 0}</span>
                      <span className="sstat-lbl">rejetés</span>
                    </div>
                  </div>
                  {scoreBreakdown && (
                    <div className="score-breakdown-wrap">
                      <div className="score-breakdown-head">
                        <span>Détail score ATS</span>
                        <span>{scoreBreakdown.formula}</span>
                      </div>
                      <div className="score-breakdown-grid">
                        <div className="score-part positive">
                          <strong>+{scoreBreakdown.confirmed_points ?? 0}</strong>
                          <span>confirmées ({scoreBreakdown.confirmed_count ?? 0})</span>
                        </div>
                        <div className="score-part positive">
                          <strong>+{scoreBreakdown.transferable_points ?? 0}</strong>
                          <span>transférables ({scoreBreakdown.transferable_count ?? 0})</span>
                        </div>
                        <div className="score-part muted">
                          <strong>+{scoreBreakdown.weak_points ?? 0}</strong>
                          <span>faibles ({scoreBreakdown.weak_count ?? 0})</span>
                        </div>
                        <div className="score-part negative">
                          <strong>{scoreBreakdown.critical_missing_penalty ?? 0}</strong>
                          <span>manquantes critiques</span>
                        </div>
                        {(scoreBreakdown.bonus_points ?? 0) > 0 && (
                          <div className="score-part bonus">
                            <strong>+{scoreBreakdown.bonus_points}</strong>
                            <span>bonus junior</span>
                          </div>
                        )}
                      </div>
                      {scoreBreakdown.critical_missing?.length > 0 && (
                        <div className="score-missing">
                          <span>À renforcer :</span>
                          {scoreBreakdown.critical_missing.slice(0, 5).join(", ")}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Output tabs */}
              {result.final_markdown && (
                <div className="output-section">
                  <div className="output-head">
                    <div className="tabs">
                      {[["cv","CV recruteur"],["audit","Audit"]].map(([id, lbl]) => (
                        <button key={id} className={`tab ${outputMode === id ? "active" : ""}`} onClick={() => setOutputMode(id)}>{lbl}</button>
                      ))}
                    </div>
                    <div className="output-actions">
                      <input className="inp inp-sm pdf-name" value={pdfFilename} onChange={e => setPdfFilename(e.target.value)} placeholder="nom_pdf" />
                      <button className="btn btn-ghost btn-sm" onClick={copyMarkdown}>⧉</button>
                      <button className="btn btn-ghost btn-sm" onClick={downloadMarkdown}>↓ .md</button>
                      <button className="btn btn-ghost btn-sm" onClick={downloadPdf} disabled={!result.output_files?.["cv_targeted.pdf"]}>↓ PDF</button>
                      <a
                        className={`btn btn-ghost btn-sm${result.output_files?.["cv_targeted.docx"] ? "" : " btn-disabled"}`}
                        href={result.output_files?.["cv_targeted.docx"] ? `/api/download/docx?filename=${encodeURIComponent(pdfFilename.trim() || "cv_targeted")}` : undefined}
                        download
                      >↓ DOCX</a>
                    </div>
                  </div>
                  <div className="output-body">
                    <textarea
                      className="inp textarea out-edit"
                      value={markdown}
                      onChange={e => setMarkdownForMode(e.target.value)}
                      spellCheck={false}
                    />
                  </div>
                  {editedMarkdown[outputMode] != null && (
                    <div className="out-edit-footer">
                      <span className="out-edit-note">✎ Texte modifié — le PDF utilise l'éditeur structuré ci-dessous</span>
                      <button className="btn btn-ghost btn-sm" onClick={() => setEditedMarkdown(prev => { const n = { ...prev }; delete n[outputMode]; return n; })}>
                        Réinitialiser
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Rejetés */}
              {audit?.rejected_bullets?.length > 0 && (
                <details className="rejected-block">
                  <summary>{audit.rejected_bullets.length} bullet(s) rejeté(s) par l'audit anti-hallucination</summary>
                  <ul className="rejected-list">
                    {audit.rejected_bullets.map((item, i) => (
                      <li key={i} className="rejected-item">
                        <span className="rejected-text">{item.bullet || "(bullet vide)"}</span>
                        {(item.reasons || []).map((reason, j) => (
                          <span key={j} className="rejected-reason">↳ {reason}</span>
                        ))}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {audit?.rejected_skills?.length > 0 && (
                <details className="rejected-block">
                  <summary>{audit.rejected_skills.length} compétence(s) rejetée(s)</summary>
                  <ul className="rejected-list">
                    {audit.rejected_skills.map((item, i) => (
                      <li key={i} className="rejected-item">
                        <span className="rejected-text">{item.skill || "(vide)"}</span>
                        {(item.reasons || []).map((reason, j) => (
                          <span key={j} className="rejected-reason">↳ {reason}</span>
                        ))}
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              {/* Éditeur PDF */}
              {editableCv && (
                <div className="editor-section">
                  <div className="editor-head">
                    <h3 className="editor-title">Édition PDF</h3>
                    <div className="editor-controls">
                      <label className="field-row">
                        <span className="flabel">Thème</span>
                        <select className="sel" value={pdfDesign.theme || "engineeringclassic"} onChange={e => setPdfDesign({ ...pdfDesign, theme: e.target.value })}>
                          <option value="engineeringclassic">Engineering Classic</option>
                          <option value="custom1">Custom 1</option>
                        </select>
                      </label>
                      <label className="field-row">
                        <span className="flabel">Preset</span>
                        <select className="sel" value={pdfDesign.preset || "classic"} onChange={e => setPdfDesign({ ...pdfDesign, preset: e.target.value })}>
                          <option value="classic">Classique</option>
                          <option value="tech">Tech</option>
                          <option value="compact">Dense ATS</option>
                          <option value="airy">Aéré</option>
                        </select>
                      </label>
                      <label className="field-row">
                        <span className="flabel">Police</span>
                        <input className="inp inp-sm" type="number" min="8.2" max="10.2" step="0.05"
                          value={pdfDesign.font_size}
                          onChange={e => setPdfDesign({ ...pdfDesign, font_size: Number(e.target.value) })} />
                      </label>
                      <label className="field-row">
                        <span className="flabel">Marges</span>
                        <select className="sel" value={pdfDesign.margin} onChange={e => setPdfDesign({ ...pdfDesign, margin: e.target.value })}>
                          <option value="compact">Compactes</option>
                          <option value="normal">Normales</option>
                          <option value="large">Larges</option>
                        </select>
                      </label>
                      <label className="field-row">
                        <span className="flabel">Couleur</span>
                        <select className="sel" value={pdfDesign.primary_color || "blue"} onChange={e => setPdfDesign({ ...pdfDesign, primary_color: e.target.value })}>
                          <option value="blue">Bleu</option>
                          <option value="slate">Ardoise</option>
                          <option value="green">Vert</option>
                          <option value="purple">Violet</option>
                          <option value="black">Noir</option>
                        </select>
                      </label>
                      <label className="toggle-row">
                        <input type="checkbox" checked={pdfDesign.show_icons !== false} onChange={e => setPdfDesign({ ...pdfDesign, show_icons: e.target.checked })} />
                        <span>Icônes</span>
                      </label>
                      <label className="toggle-row">
                        <input type="checkbox" checked={!!pdfDesign.underline_links} onChange={e => setPdfDesign({ ...pdfDesign, underline_links: e.target.checked })} />
                        <span>Liens soulignés</span>
                      </label>
                      <button className="btn btn-sec btn-sm" onClick={() => applyDesignPreset("fill")} disabled={loading}>Remplir</button>
                      <button className="btn btn-sec btn-sm" onClick={() => applyDesignPreset("compact")} disabled={loading}>Compacter</button>
                      <button className="btn btn-pri" onClick={updatePdf} disabled={loading}>Mettre à jour</button>
                    </div>
                  </div>
                  <div className="editor-body">
                    <div className="editor-fields">
                      <div className="section-toggles">
                        {SECTION_LABELS.map(name => (
                          <label key={name} className={`section-toggle ${editableCv.sections?.[name] ? "on" : "off"}`}>
                            <input type="checkbox" checked={!!editableCv.sections?.[name]} onChange={() => toggleSection(name)} />
                            <span>{name}</span>
                          </label>
                        ))}
                      </div>
                      {editableCv.sections?.["Résumé"] && (
                        <label className="field">
                          <span className="flabel">Résumé</span>
                          <textarea className="inp textarea ta-sm"
                            value={editableCv.sections?.["Résumé"]?.[0] || ""}
                            onChange={e => patchSection("Résumé", [e.target.value])} />
                        </label>
                      )}
                      {editableCv.sections?.["Compétences clés"] && (
                        <div className="edit-block">
                          <div className="edit-block-head">
                            <span className="flabel">Compétences</span>
                            <button className="btn btn-ghost btn-sm" onClick={addSkill}>+ compétence</button>
                          </div>
                          {(editableCv.sections?.["Compétences clés"] || []).map((skill, i) => (
                            <div className="skill-row" key={i}>
                              <input className="inp inp-skill-label" value={skill.label || ""} onChange={e => patchSkill(i, { label: e.target.value })} placeholder="Label" />
                              <input className="inp" value={skill.details || ""} onChange={e => patchSkill(i, { details: e.target.value })} placeholder="Détails" />
                              <button className="btn btn-icon" onClick={() => removeSkill(i)}>✕</button>
                            </div>
                          ))}
                        </div>
                      )}
                      {(editableCv.sections?.["Expérience"] || []).map((exp, i) => (
                        <div className="exp-block" key={i}>
                          <div className="exp-title-row">
                            <span className="exp-title">{exp.position || "Expérience"}</span>
                            <div className="exp-actions">
                              <button className="btn btn-ghost btn-sm" onClick={() => moveExperience(i, -1)} disabled={i === 0}>↑</button>
                              <button className="btn btn-ghost btn-sm" onClick={() => moveExperience(i, 1)} disabled={i === (editableCv.sections?.["Expérience"] || []).length - 1}>↓</button>
                            </div>
                          </div>
                          <div className="inline-row">
                            <input className="inp" value={exp.position || ""} onChange={e => patchExp(i, { position: e.target.value })} placeholder="Poste" />
                            <input className="inp" value={exp.company  || ""} onChange={e => patchExp(i, { company:  e.target.value })} placeholder="Entreprise" />
                            <input className="inp inp-sm" value={exp.date || ""} onChange={e => patchExp(i, { date: e.target.value })} placeholder="Date" />
                          </div>
                          <div className="bullet-list">
                            {(exp.highlights || []).map((bullet, j) => (
                              <div className="bullet-row" key={j}>
                                <textarea className="inp textarea bullet-ta" value={bullet} onChange={e => patchBullet(i, j, e.target.value)} />
                                <button className="btn btn-icon" onClick={() => removeBullet(i, j)}>✕</button>
                              </div>
                            ))}
                            <button className="btn btn-ghost btn-sm add-line" onClick={() => addBullet(i)}>+ bullet</button>
                          </div>
                        </div>
                      ))}
                      {editableCv.sections?.["Formation"] && (
                        <label className="field">
                          <span className="flabel">Formation <em className="hint-em">institution | diplôme | date</em></span>
                          <textarea className="inp textarea ta-sm"
                            value={(editableCv.sections?.["Formation"] || []).map(it => [it.institution, it.area, it.date].filter(Boolean).join(" | ")).join("\n")}
                            onChange={e => {
                              const entries = e.target.value.split("\n").map(l => {
                                const [institution, area, date] = l.split("|").map(p => p.trim());
                                return { institution, area, date };
                              }).filter(it => it.institution || it.area || it.date);
                              patchSection("Formation", entries);
                            }} />
                        </label>
                      )}
                    </div>
                    <iframe
                      key={pdfKey}
                      className="pdf-frame"
                      title="Aperçu PDF"
                      src={activeHistoryId ? `/api/history/${activeHistoryId}/pdf?v=${pdfKey}` : `/api/preview/pdf?v=${pdfKey}`}
                    />
                  </div>
                </div>
              )}
            </>
          )}

        </div>
      </main>

    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
