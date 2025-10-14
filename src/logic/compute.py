def to_svg(points, title="결과", w=600, h=300, pad=30):
    # 간단 폴리라인 SVG 생성(순수 파이썬)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(1, max_x - min_x)
    span_y = max(1, max_y - min_y)

    def sx(x): return pad + (x - min_x) * (w - 2*pad) / span_x
    def sy(y): return h - pad - (y - min_y) * (h - 2*pad) / span_y

    poly = " ".join(f"{sx(x)},{sy(y)}" for x, y in points)

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">
  <rect width="100%" height="100%" fill="white"/>
  <polyline points="{poly}" fill="none" stroke="black" stroke-width="2"/>
  <text x="{w/2}" y="{pad}" text-anchor="middle" font-size="16">{escape_xml(title)}</text>
</svg>""".strip()
    return svg


def escape_xml(text: str) -> str:
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&apos;"))
