#let header-blue = rgb("#314061")

#let contact-icon(icon-name) = box(
  width: 13pt,
  height: 13pt,
  radius: 50%,
  fill: white,
)[
  #align(center + horizon)[
    #text(fill: header-blue, size: 6.8pt, top-edge: "bounds", bottom-edge: "bounds")[#fa-icon(icon-name)]
  ]
]

#let contact-item(icon-name, body) = box[
  #grid(
    columns: (auto, auto),
    gutter: 0.12cm,
    align: horizon,
  )[
    #contact-icon(icon-name)
  ][
    #box[
      #body
    ]
  ]
]

#block(
  width: 100%,
  fill: header-blue,
  inset: (left: 0.95cm, right: 0.95cm, top: 0.95cm, bottom: 0.58cm),
)[
  #grid(
    columns: (3.0cm, 1fr),
    gutter: 0.52cm,
    align: top,
  )[
    {% if cv.photo %}
    #box(
      width: 3.0cm,
      height: 3.0cm,
      radius: 6pt,
      clip: true,
    )[
      #image("{{ cv.photo.name }}", width: 3.0cm, height: 3.0cm, fit: "cover")
    ]
    {% endif %}
  ][
    #v(0.03cm)

    #box(width: 100%)[
      #text(fill: white, size: 16pt, weight: "bold")[{{ cv.name }}]
      #h(0.20cm)
      {% if cv.headline %}
      #text(fill: white, size: 9.1pt, style: "italic")[{{ cv.headline }}]
      {% endif %}
    ]

    #v(0.24cm)

    #block(width: 100%)[
      #set text(fill: white, size: 8.1pt)
      {% if cv.email %}
      #contact-item("envelope", [#link("mailto:{{ cv.email }}", icon: false, if-underline: false, if-color: false)[{{ cv.email|replace("@", "\\@") }}]])
      #h(0.32cm)
      {% endif %}
      {% if cv.phone %}
      #contact-item("phone", [#link("tel:{{ cv.phone }}", icon: false, if-underline: false, if-color: false)[{{ cv.phone }}]])
      #h(0.32cm)
      {% endif %}
      {% if cv.location %}
      #contact-item("location-dot", [{{ cv.location }}])
      #h(0.32cm)
      {% endif %}
      {% for sn in cv.social_networks %}
        {% if sn.network == "LinkedIn" %}
      #contact-item("linkedin-in", [#link("https://www.linkedin.com/in/{{ sn.username }}", icon: false, if-underline: false, if-color: false)[Linkedin]])
      #h(0.32cm)
        {% elif sn.network == "GitHub" %}
      #contact-item("link", [#link("https://github.com/{{ sn.username }}", icon: false, if-underline: false, if-color: false)[Github]])
      #h(0.32cm)
        {% endif %}
      {% endfor %}
    ]
  ]
]
