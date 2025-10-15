from workers import WorkerEntrypoint, Response, Request
from urllib.parse import urlparse
import json

# 상대임포트 대신 절대임포트(패키지 구조 필요: src/logic/__init__.py 존재)
from logic.compute import to_svg


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlparse(request.url).path

        # 1) 헬스체크
        if path == "/api/health":
            return Response.json({"ok": True})

        # 2) JSON 입력 → SVG → HTML
        if path == "/api/process" and request.method == "POST":
            try:
                body = await request.json()
            except Exception:
                return Response.json({"ok": False, "error": "invalid json"}, status=400)

            title = body.get("title", "결과")
            points = body.get("points", [[0, 0], [10, 20], [20, 10], [30, 30]])

            svg = to_svg(points, title)
            html = f"""<!doctype html>
<html lang="ko"><meta charset="utf-8" />
<body style="font-family:sans-serif">
  <h2>{title}</h2>
  <p>입력 포인트 개수: {len(points)}개</p>
  <img alt="결과 그래프" src="data:image/svg+xml;base64,{self._b64(svg)}" />
</body></html>"""
            return Response(html, headers={"content-type": "text/html; charset=utf-8"})

        # 3) multipart 업로드 (파일/텍스트 혼합)
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

        # 4) 정적 자산 서빙: ASSETS 바인딩 사용
        #    우선 그대로 시도 → 404면 /index.html 폴백
        asset_resp = await self.env.ASSETS.fetch(request)
        if asset_resp.status == 404 and path == "/":
            parsed = urlparse(request.url)
            index_url = f"{parsed.scheme}://{parsed.netloc}/index.html"
            index_req = Request(index_url, method="GET")
            asset_resp = await self.env.ASSETS.fetch(index_req)

        if asset_resp.status != 404:
            return asset_resp

        return Response("Not Found", status=404)

    # 작은 유틸 (Pyodide 호환용)
    def _b64(self, s: str) -> str:
        import base64
        return base64.b64encode(s.encode("utf-8")).decode("ascii")
