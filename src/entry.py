# -*- coding: utf-8 -*-
from workers import WorkerEntrypoint, Response, Request
from urllib.parse import urlparse
import json

from logic.compute import run_simulation

# 공통 헤더(필요 시 도메인으로 제한하세요)
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # CORS 프리플라이트
        if request.method == "OPTIONS":
            return Response("", headers=CORS)

        path = urlparse(request.url).path

        # 헬스체크
        if path == "/api/health":
            return Response.json({"ok": True}, headers=CORS)

        # 시뮬레이션 API
        # POST /api/simulate
        # body: { "GAME_ID": 1, "GOAL": 7, "OBS_TOTAL": 888, "N_SIMS"?: int, "SEED"?: int, "BINS"?: int }
        if path == "/api/simulate" and request.method == "POST":
            try:
                body = await request.json()
            except Exception:
                return Response.json({"ok": False, "error": "invalid json"}, status=400, headers=CORS)

            try:
                game_id  = int(body.get("GAME_ID"))
                goal     = int(body.get("GOAL"))
                obs_tot  = int(body.get("OBS_TOTAL"))
                n_sims   = int(body.get("N_SIMS", 500_000))
                seed     = int(body.get("SEED", 20251014))
                bins     = int(body.get("BINS", 128))

                # 안전 상한 (Python Workers CPU/벽시계 시간 고려)
                n_sims = max(10_000, min(n_sims, 2_000_000))

                summary, svg = run_simulation(
                    game_id=game_id, goal=goal, obs_total=obs_tot,
                    n_sims=n_sims, seed=seed, bins=bins
                )
            except Exception as e:
                return Response.json({"ok": False, "error": str(e)}, status=400, headers=CORS)

            # 권장: base64 data URL 대신 '생 SVG 문자열'을 그대로 전달
            # 프런트에서 Blob(URL.createObjectURL)로 <img src>에 붙이세요.
            return Response.json(
                {"ok": True, "summary": summary, "image_svg": svg},
                headers=CORS
            )

        # 정적 자산 (assets/) — ASSETS 바인딩 필요 (wrangler.toml)
        asset_resp = await self.env.ASSETS.fetch(request)
        if asset_resp.status == 404 and path == "/":
            # / → /index.html 폴백
            parsed = urlparse(request.url)
            index_url = f"{parsed.scheme}://{parsed.netloc}/index.html"
            index_req = Request(index_url, method="GET")
            asset_resp = await self.env.ASSETS.fetch(index_req)
        if asset_resp.status != 404:
            # 정적 응답에도 CORS 부여(필요 시 삭제 가능)
            # 일부 런타임에선 Response 헤더 수정이 제한될 수 있어 그대로 반환
            return asset_resp

        return Response("Not Found", status=404, headers=CORS)
