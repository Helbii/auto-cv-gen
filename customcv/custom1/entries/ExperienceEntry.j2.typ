{%- set side = entry.date_and_location_column -%}
{%- set side_lines = side.splitlines() -%}
{%- if side_lines | length >= 2 -%}
{%- set side = side_lines[1] ~ " | " ~ side_lines[0] -%}
{%- endif -%}
#block(width: 100%, below: 0.32cm)[
  #set text(size: cv-body-size)
  // Un seul rythme : leading (wrap) == spacing (entre blocs) => espacement uniforme
  #set par(leading: cv-rhythm)
  #set block(spacing: cv-rhythm)
  #grid(
    columns: (1fr, 4.25cm),
    gutter: 0.18cm,
    align: top,
  )[
    #block[#strong[{{ entry.company }}], #emph[{{ entry.position }}]]
    {% if entry.summary %}
    #block[{{ entry.summary }}]
    {% endif %}
    {% if entry.mission_title %}
    #block[#strong[{{ entry.mission_title }}]]
    {% endif %}
    {% for highlight in entry.highlights %}
    #block[
      #grid(
        columns: (0.30cm, 1fr),
        gutter: 0pt,
        align: top,
      )[
        •
      ][
        {{ highlight }}
      ]
    ]
    {% endfor %}
    {% if entry.stack %}
    #block[
      #set par(leading: 0.95em)
      #strong[Stack] :#h(0.10cm)
      {%- for tech in entry.stack.split(", ") -%}
      #box(stroke: rgb("#394055") + 0.7pt, radius: 2pt, inset: (x: 0.11cm, y: 0.04cm), outset: (y: 0.03cm))[#text(size: 7.7pt)[{{ tech }}]]#h(0.10cm)
      {%- endfor -%}
    ]
    {% endif %}
  ][
    #align(right)[
      #text(size: 8.1pt, fill: rgb("#394055"))[{{ side }}]
    ]
  ]
]
