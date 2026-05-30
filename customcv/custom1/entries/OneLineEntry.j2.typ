{%- set label_lower = entry.label | lower -%}
{%- if label_lower == "langues" -%}
{%- for item in entry.details.split(" | ") -%}
{%- set parts = item.split(": ", 1) -%}
#box(
  stroke: rgb("#394055") + 0.8pt,
  radius: 2.5pt,
  inset: (x: 0.20cm, y: 0.075cm),
)[
  #text(size: 8.1pt)[
    #strong[{{ parts[0] }}]
    #text[: {{ parts[1] }}]
  ]
]
#h(0.14cm)
{%- endfor -%}
{%- else %}
#block(width: 100%, below: 0.13cm)[
  #set par(leading: cv-rhythm)
  #set block(spacing: cv-rhythm)
  #text(size: cv-body-size)[
    #strong[{{ entry.label }}]
    #h(0.03cm)
    #text[({{ entry.details }})]
  ]
]
{%- endif %}
