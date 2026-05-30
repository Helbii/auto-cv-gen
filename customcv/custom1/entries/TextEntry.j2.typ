#block(width: 100%, below: 0cm)[
  #set par(leading: cv-rhythm)
  #set block(spacing: cv-rhythm)
  #set text(size: cv-body-size)
{% if entry.main_column is defined %}
{% for line in entry.main_column.splitlines() %}
  {{ line }}{% if not loop.last %}#linebreak(){% endif %}
{% endfor %}
{% else %}
{% for line in entry.splitlines() %}
  {{ line }}{% if not loop.last %}#linebreak(){% endif %}
{% endfor %}
{% endif %}
]
