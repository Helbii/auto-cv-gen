{% set section_icon = "diamond" %}
{% if "experience" in snake_case_section_title or "expérience" in snake_case_section_title %}
{% set section_icon = "briefcase" %}
{% elif "formation" in snake_case_section_title or "education" in snake_case_section_title %}
{% set section_icon = "graduation-cap" %}
{% elif "competence" in snake_case_section_title or "compétence" in snake_case_section_title %}
{% set section_icon = "brain" %}
{% elif "langue" in snake_case_section_title or "language" in snake_case_section_title %}
{% set section_icon = "globe" %}
{% elif "projet" in snake_case_section_title or "project" in snake_case_section_title %}
{% set section_icon = "code" %}
{% endif %}

#block(
  width: 100%,
  inset: (left: 0.95cm, right: 0.95cm),
)[

{% if snake_case_section_title in ["profil", "profile", "resume", "résumé", "summary"] %}
#v(0.70cm)
{% else %}
#v(0.25cm)
#grid(
  columns: (auto, 1fr),
  gutter: 0.16cm,
  align: horizon,
)[
  #box(
    width: 13.5pt,
    height: 13.5pt,
    fill: rgb("#ef5670"),
    radius: 50%,
  )[
    #align(center + horizon)[
      #text(fill: white, size: 7pt, top-edge: "bounds", bottom-edge: "bounds")[#fa-icon("{{ section_icon }}")]
    ]
  ]
][
  #text(fill: rgb("#ef5670"), size: 14.2pt, weight: "bold")[{{ section_title }}]
]
#v(0.13cm)
{% endif %}
