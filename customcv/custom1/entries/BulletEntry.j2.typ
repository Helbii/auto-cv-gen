#block(width: 100%, below: 0.05cm)[
  #set par(leading: cv-rhythm)
  #set block(spacing: cv-rhythm)
  #set text(size: cv-body-size)
{% if entry.main_column is defined %}
{% for line in entry.main_column.splitlines() %}
  {{ line }}
{% endfor %}
{% else %}
  {{ entry }}
{% endif %}
]