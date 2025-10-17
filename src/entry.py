# -*- coding: utf-8 -*-
from workers import WorkerEntrypoint, Response, Request
from urllib.parse import urlparse
import json

# 공통 헤더(필요 시 도메인으로 제한하세요)
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # 서버 변수
        store = self.env.GLOBAL_STORE
        count = int(await store.get("count") or "0")
        count += 1
        await store.put("count", str(count))

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
            # 메모리 정리 강제 실행
            import gc
            gc.collect()

            try:
                from logic.compute import run_simulation, build_pity_cdf, load_precomputed_from_assets, load_precomputed_from_kv
            except Exception as e:
                return Response.json({"ok": False, "error": f"import failed: {e}"}, status=500, headers=CORS)

            try:
                body = await request.json()
            except Exception:
                return Response.json({"ok": False, "error": "invalid json"}, status=400, headers=CORS)

            try:
                game_id  = int(body.get("GAME_ID"))
                goal     = int(body.get("GOAL"))
                obs_tot  = int(body.get("OBS_TOTAL"))

                # 1순위: Assets에서 사전 계산된 데이터 로드 (~1-3ms)
                precomputed_data = await load_precomputed_from_assets(self.env.ASSETS, game_id, goal)

                # 2순위: KV 폴백 (Assets에 없는 경우)
                if not precomputed_data:
                    precomputed_data = await load_precomputed_from_kv(store, game_id, goal)

                # CDF 캐싱 - 게임 ID별 키 사용
                cdf_key = f"cdf_{game_id}"
                cdf_str = await store.get(cdf_key)

                if cdf_str:
                    cdf = json.loads(cdf_str)
                else:
                    cdf = build_pity_cdf(game_id)
                    await store.put(cdf_key, json.dumps(cdf))

                summary, svg = run_simulation(
                    game_id=game_id,
                    goal=goal,
                    obs_total=obs_tot,
                    cdf=cdf,
                    kv_store=store,
                    precomputed_data=precomputed_data
                )

                # 데이터 소스 결정
                if precomputed_data:
                    data_source = "Assets precomputed"
                else:
                    data_source = "live simulation"

                print(f"[Request #{count}] game_id={game_id}, goal={goal}, obs_total={obs_tot} ({data_source})")
                print(f"Summary: {summary.get('percentile_rank_of_obs_%', 'N/A')}")

                # 시뮬레이션 후 메모리 정리
                gc.collect()

            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                print(f"[Error #{count}] {error_details}")
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
