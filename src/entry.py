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
            import time
            request_timings = {}
            t_request_start = time.perf_counter()

            # 메모리 정리 강제 실행
            import gc
            gc.collect()

            try:
                from logic.compute import run_simulation
                from logic.compute_not_used import build_pity_cdf, load_precomputed_from_assets, load_precomputed_from_kv
            except Exception as e:
                return Response.json({"ok": False, "error": f"import failed: {e}"}, status=500, headers=CORS)

            try:
                t0 = time.perf_counter()
                body = await request.json()
                request_timings["0_parse_request_ms"] = (time.perf_counter() - t0) * 1000
            except Exception:
                return Response.json({"ok": False, "error": "invalid json"}, status=400, headers=CORS)

            try:
                game_id  = int(body.get("GAME_ID"))
                goal     = int(body.get("GOAL"))
                obs_tot  = int(body.get("OBS_TOTAL"))

                # Assets에서 사전 계산된 데이터 로드 (~1-3ms)
                t1 = time.perf_counter()
                precomputed_data = await load_precomputed_from_assets(self.env.ASSETS, game_id, goal)
                request_timings["1_load_assets_ms"] = (time.perf_counter() - t1) * 1000

                # 데이터가 없으면 에러 반환 (실시간 시뮬레이션 비활성화)
                if not precomputed_data:
                    return Response.json({
                        "ok": False,
                        "error": f"No precomputed data for game_id={game_id}, goal={goal}. Please use goal between 1-20."
                    }, status=400, headers=CORS)

                # CDF 캐싱 - 게임 ID별 키 사용
                t2 = time.perf_counter()
                cdf_key = f"cdf_{game_id}"
                cdf_str = await store.get(cdf_key)

                if cdf_str:
                    cdf = json.loads(cdf_str)
                else:
                    cdf = build_pity_cdf(game_id)
                    await store.put(cdf_key, json.dumps(cdf))
                request_timings["2_cdf_cache_ms"] = (time.perf_counter() - t2) * 1000

                # 시뮬레이션 실행 (compute.py에서 시간 측정)
                t3 = time.perf_counter()
                summary, svg, compute_timings = run_simulation(
                    game_id=game_id,
                    goal=goal,
                    obs_total=obs_tot,
                    precomputed_data=precomputed_data
                )
                request_timings["3_run_simulation_total_ms"] = (time.perf_counter() - t3) * 1000
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                print(f"[Error #{count}] {error_details}")
                return Response.json({"ok": False, "error": "01_ "+str(e)}, status=400, headers=CORS)
            try:
                # 데이터 소스 결정
                if precomputed_data:
                    data_source = "Assets precomputed"
                else:
                    data_source = "live simulation"

                print(f"[Request #{count}] game_id={game_id}, goal={goal}, obs_total={obs_tot} ({data_source})")
                print(f"Summary: {summary.get('percentile_rank_of_obs_%', 'N/A')}")

                # 시뮬레이션 후 메모리 정리
                gc.collect()

                # 전체 요청 처리 시간
                request_timings["4_total_request_ms"] = (time.perf_counter() - t_request_start) * 1000

                # compute_timings를 request_timings에 병합
                all_timings = {**request_timings, **compute_timings}

            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                print(f"[Error #{count}] {error_details}")
                return Response.json({"ok": False, "error": "02_ "+str(e)}, status=400, headers=CORS)

            # 권장: base64 data URL 대신 '생 SVG 문자열'을 그대로 전달
            # 프런트에서 Blob(URL.createObjectURL)로 <img src>에 붙이세요.
            return Response.json(
                {"ok": True, "summary": summary, "image_svg": svg, "timings": all_timings},
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
