{% set lines = entry.date_and_location_column.splitlines() %}
{% set side = entry.date_and_location_column %}
{% if lines | length >= 2 %}
  {% set side = lines[1] ~ " | " ~ lines[0] %}
{% endif %}

#block(width: 100%, below: 0.09cm)[
  #set par(leading: cv-rhythm)
  #set block(spacing: cv-rhythm)
  #set text(size: cv-body-size)

  #grid(
    columns: (1fr, 4.25cm),
    gutter: 0.18cm,
    align: top,
  )[
{% for line in entry.main_column.splitlines() %}
    {{ line }}
{% endfor %}
  ][
    #align(right)[
      #text(size: 8.1pt, fill: rgb("#394055"))[
        {{ side }}
      ]
    ]
  ]
]