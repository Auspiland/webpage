# -*- coding: utf-8 -*-
from workers import WorkerEntrypoint, Response, Request
from urllib.parse import urlparse
import base64
import json

from logic.compute import run_simulation

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlparse(request.url).path

        # 헬스체크
        if path == "/api/health":
            return Response.json({"ok": True})

        # 시뮬레이션 API
        # POST /api/simulate
        # body: { "GAME_ID": 1, "GOAL": 7, "OBS_TOTAL": 888, "N_SIMS"?: int, "SEED"?: int, "BINS"?: int }
        if path == "/api/simulate" and request.method == "POST":
            try:
                body = await request.json()
            except Exception:
                return Response.json({"ok": False, "error": "invalid json"}, status=400)

            try:
                game_id  = int(body.get("GAME_ID"))
                goal     = int(body.get("GOAL"))
                obs_tot  = int(body.get("OBS_TOTAL"))
                n_sims   = int(body.get("N_SIMS", 500_000))
                seed     = int(body.get("SEED", 20251014))
                bins     = int(body.get("BINS", 128))

                # 안전 상한 (Workers CPU 시간 대비)
                n_sims = max(10_000, min(n_sims, 2_000_000))

                summary, svg = run_simulation(
                    game_id=game_id, goal=goal, obs_total=obs_tot,
                    n_sims=n_sims, seed=seed, bins=bins
                )
            except Exception as e:
                return Response.json({"ok": False, "error": str(e)}, status=400)

            # 브라우저에서 곧바로 표시 가능하도록 data URL 포함
            svg_b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
            data_url = f"data:image/svg+xml;base64,{svg_b64}"

            return Response.json({
                "ok": True,
                "summary": summary,
                "image_data_url": data_url
            })

        # 정적 자산 (assets/)
        asset_resp = await self.env.ASSETS.fetch(request)
        if asset_resp.status == 404 and path == "/":
            # / → /index.html 폴백
            from urllib.parse import urlparse
            parsed = urlparse(request.url)
            index_url = f"{parsed.scheme}://{parsed.netloc}/index.html"
            index_req = Request(index_url, method="GET")
            asset_resp = await self.env.ASSETS.fetch(index_req)
        if asset_resp.status != 404:
            return asset_resp

        return Response("Not Found", status=404)
