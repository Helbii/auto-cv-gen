#block(width: 100%, below: 0.13cm)[
  #set par(leading: cv-rhythm)
  #set block(spacing: cv-rhythm)

  #grid(
    columns: (1fr, 3.15cm),
    gutter: 0.20cm,
    align: top,
  )[
    #text(size: cv-body-size)[
    #strong[{{ entry.institution }}]
    #text[, ]
    {% if entry.degree %}
    #emph[{{ entry.degree }} en {{ entry.area }}]
    {% else %}
    #emph[{{ entry.area }}]
    {% endif %}
    ]
  ][
    #align(right)[
      #text(size: 8.0pt, fill: rgb("#394055"))[
{% for line in entry.date_and_location_column.splitlines() %}
        {{ line }}
{% endfor %}
      ]
    ]
  ]
]
