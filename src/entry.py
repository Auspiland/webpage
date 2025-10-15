# -*- coding: utf-8 -*-
from workers import WorkerEntrypoint, Response, Request
from urllib.parse import urlparse
import json
import gc

# 공통 헤더(필요 시 도메인으로 제한하세요)
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

# 모듈 import를 최상단으로 이동 (매번 import 방지)
from logic.compute import run_simulation, build_pity_cdf

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
            gc.collect()
            
            try:
                body = await request.json()
            except Exception:
                return Response.json({"ok": False, "error": "invalid json"}, status=400, headers=CORS)

            try:
                game_id  = int(body.get("GAME_ID"))
                goal     = int(body.get("GOAL"))
                obs_tot  = int(body.get("OBS_TOTAL"))

                # 입력값 검증
                if goal <= 0:
                    return Response.json({"ok": False, "error": "GOAL must be positive"}, status=400, headers=CORS)
                if obs_tot < 0:
                    return Response.json({"ok": False, "error": "OBS_TOTAL must be non-negative"}, status=400, headers=CORS)
                if game_id not in [1, 2]:
                    return Response.json({"ok": False, "error": "GAME_ID must be 1 or 2"}, status=400, headers=CORS)

                # CDF 캐싱 - 게임 ID별 키 사용
                # cdf_key = f"cdf_{game_id}"
                # cdf_str = await store.get(cdf_key)

                # if cdf_str:
                #     cdf = json.loads(cdf_str)
                # else:
                #     cdf = build_pity_cdf(game_id)
                #     await store.put(cdf_key, json.dumps(cdf))

                summary, svg = run_simulation(
                    game_id=game_id, goal=goal, obs_total=obs_tot
                )
                print(f"[Request #{count}] game_id={game_id}, goal={goal}, obs_total={obs_tot}")
                print(f"Summary: {summary.get('percentile_rank_of_obs_%', 'N/A')}")

            except ValueError as e:
                # 입력값 검증 에러 (400)
                import traceback
                error_details = traceback.format_exc()
                print(f"[ValueError #{count}] {error_details}")
                return Response.json(
                    {"ok": False, "error": str(e), "type": "ValueError"},
                    status=400,
                    headers=CORS
                )
            except MemoryError as e:
                # 메모리 부족 에러 (507)
                import traceback
                error_details = traceback.format_exc()
                print(f"[MemoryError #{count}] {error_details}")
                gc.collect()  # 즉시 메모리 정리
                return Response.json(
                    {"ok": False, "error": "Memory limit exceeded. Try reducing parameters.", "type": "MemoryError"},
                    status=507,
                    headers=CORS
                )
            except Exception as e:
                # 기타 서버 에러 (500)
                import traceback
                error_details = traceback.format_exc()
                print(f"[Error #{count}] {error_details}")
                return Response.json(
                    {"ok": False, "error": str(e), "type": type(e).__name__, "traceback": error_details[:500]},
                    status=500,
                    headers=CORS
                )

            # 권장: base64 data URL 대신 '생 SVG 문자열'을 그대로 전달
            # 프런트에서 Blob(URL.createObjectURL)로 <img src>에 붙이세요.
            result = Response.json(
                {"ok": True, "summary": summary, "image_svg": svg},
                headers=CORS
            )

            # 명시적으로 변수 해제 후 메모리 정리
            del summary, svg
            gc.collect()

            return result

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
