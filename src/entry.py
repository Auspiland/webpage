from workers import WorkerEntrypoint, Response
from workers.assets import get_asset
from urllib.parse import urlparse
import json
from .logic.compute import to_svg

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlparse(request.url).path

        # 1) 헬스체크
        if path == "/api/health":
            return Response.json({"ok": True})

        # 2) JSON 입력 → SVG 이미지 + 텍스트 포함 HTML 응답
        if path == "/api/process" and request.method == "POST":
            try:
                body = await request.json()
            except Exception:
                return Response.json({"ok": False, "error": "invalid json"}, status=400)

            title = body.get("title", "결과")
            points = body.get("points", [[0,0],[10,20],[20,10],[30,30]])

            svg = to_svg(points, title)
            html = f"""<!doctype html>
<html lang="ko"><meta charset="utf-8" />
<body style="font-family:sans-serif">
  <h2>{title}</h2>
  <p>입력 포인트 개수: {len(points)}개</p>
  <img alt="결과 그래프" src="data:image/svg+xml;base64,{self._b64(svg)}" />
</body></html>"""
            return Response(html, headers={"content-type": "text/html; charset=utf-8"})

        # 3) multipart 업로드 샘플(파일/텍스트 혼합)
        if path == "/api/upload" and request.method == "POST":
            form = await request.formData()
            note = form.get("note")
            file = form.get("file")  # File 객체
            return Response.json({
                "ok": True,
                "note": note,
                "fileName": getattr(file, "name", None),
                "fileType": getattr(file, "type", None),
                "fileSize": getattr(file, "size", None),
            })

        # 4) 정적 자산 서빙(assets/)
        try:
            asset_path = path if path != "/" else "/index.html"
            asset = await get_asset(self, asset_path)
            return Response(asset.body, headers=asset.headers)
        except Exception:
            return Response("Not Found", status=404)

    # 작은 유틸 (Pyodide 호환용)
    def _b64(self, s: str) -> str:
        import base64
        return base64.b64encode(s.encode("utf-8")).decode("ascii")
