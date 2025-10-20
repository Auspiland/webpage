# -*- coding: utf-8 -*-
from math import sqrt
from typing import Dict, Tuple, List

# ---- GAME_ID별 기본 파라미터 ----
GAME_TABLE = {
    1: dict(CEIL_RATIO=0.5,  MAX_T=80, BASE_P=0.008, ACCEL_START=63, ACCEL_STEP=0.06),
    2: dict(CEIL_RATIO=0.55, MAX_T=90, BASE_P=0.006, ACCEL_START=73, ACCEL_STEP=0.06),
}

N_SIMS = 1_000_000  # 고정밀 시뮬레이션
SEED = 31014646
BINS = 300


# ---------- 데이터 압축/해제 (빈도 리스트) ----------
def decompress_totals(min_val: int, freq: List[int]) -> List[int]:
    """빈도 리스트에서 원본 totals 완벽 복원

    Args:
        min_val: 최소값
        freq: 빈도 리스트

    Returns:
        재구성된 totals 리스트 (원본과 100% 동일한 분포)
    """
    totals = []
    for i, count in enumerate(freq):
        if count > 0:
            value = min_val + i
            totals.extend([value] * count)
    return totals


def make_hist_svg(totals, obs_total, bins=128, title=""):
    """히스토그램 SVG 생성 (정규분포 제거)

    Args:
        totals: 시뮬레이션 데이터 리스트
        obs_total: 관측된 값 (빨간 수직선 표시)
        bins: 히스토그램 구간 수
        title: 차트 제목

    Returns:
        svg_string
    """
    if not totals:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450"></svg>'

    # 히스토그램(density)
    x_min, x_max = min(totals), max(totals)
    if x_max == x_min:
        x_min -= 0.5; x_max += 0.5
    bins = max(32, min(int(bins), 256))
    width = (x_max - x_min) / float(bins)
    edges = [x_min + i * width for i in range(bins + 1)]
    counts = [0] * bins
    for v in totals:
        i = int((v - x_min) / width)
        if i == bins: i -= 1
        counts[i] += 1
    n = len(totals)
    density = [c / (n * width) for c in counts]

    # SVG 좌표
    W, H = 800, 450
    L, R, T, B = 60, 20, 30, 50
    innerW, innerH = W - L - R, H - T - B

    # y 스케일
    y_max = max(density) if density else 1.0

    def sx(x): return L + (x - x_min) * (innerW / max(1e-9, (x_max - x_min)))
    def sy(y): return T + innerH - y * (innerH / y_max)

    # 히스토그램 path
    y0 = 0.0
    threshold = y_max * 1e-5
    path_parts = [f"M {sx(edges[0]):.2f} {sy(0.0):.2f}"]
    for i, d in enumerate(density):
        x1 = edges[i+1]
        d_val = 0.0 if d < threshold else d
        path_parts.extend([f"L {sx(x1):.2f} {sy(y0):.2f}", f"L {sx(x1):.2f} {sy(d_val):.2f}"])
        y0 = d_val
    path_parts.append(f"L {sx(edges[-1]):.2f} {sy(0):.2f} Z")
    area_path = " ".join(path_parts)

    # 관측치 수직선
    ox = sx(min(max(obs_total, x_min), x_max))
    obs_line = f'<line x1="{ox:.2f}" y1="{T}" x2="{ox:.2f}" y2="{T+innerH}" stroke="#c62828" stroke-dasharray="6 4" stroke-width="2"/>'

    # 축/레이블
    mid_w, mid_h = L + innerW / 2, T + innerH / 2
    bottom_y = T + innerH
    axes = [
        f'<line x1="{L}" y1="{bottom_y}" x2="{L+innerW}" y2="{bottom_y}" stroke="black"/>',
        f'<line x1="{L}" y1="{T}" x2="{L}" y2="{bottom_y}" stroke="black"/>',
        f'<text x="{mid_w:.2f}" y="{H-8}" text-anchor="middle" font-size="12">Total draws</text>',
        f'<text x="16" y="{mid_h:.2f}" transform="rotate(-90 16,{mid_h:.2f})" font-size="12">Density</text>',
        f'<text x="{W/2:.2f}" y="20" text-anchor="middle" font-size="16">{title}</text>',
    ]

    # ticks
    x_range = x_max - x_min
    tick_y1, tick_y2 = bottom_y, bottom_y + 6
    ticks = []
    for i in range(6):
        vx = x_min + x_range * i / 5.0
        tx = sx(vx)
        ticks.extend([
            f'<line x1="{tx:.2f}" y1="{tick_y1}" x2="{tx:.2f}" y2="{tick_y2}" stroke="black"/>',
            f'<text x="{tx:.2f}" y="{tick_y2+16}" text-anchor="middle" font-size="11">{int(round(vx))}</text>'
        ])

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">
  <rect x="0" y="0" width="{W}" height="{H}" fill="white"/>
  {''.join(axes)}
  <path d="{area_path}" fill="black" opacity="0.14" stroke="none"/>
  {obs_line}
  {''.join(ticks)}
</svg>'''
    return svg


# ---------- 요약 ----------
def summarize(totals: List[int], obs_total: int, n_sims: int) -> Dict:
    """시뮬레이션 결과 통계 요약

    Args:
        totals: 시뮬레이션 데이터 리스트
        obs_total: 관측된 총 뽑기 횟수
        n_sims: 시뮬레이션 횟수

    Returns:
        통계 요약 딕셔너리
    """
    n = len(totals)
    if n == 0:
        return {
            "samples": int(n_sims),
            "obs_total_draws": int(obs_total),
            "mean_total_draws": float("nan"),
            "std_total_draws": float("nan"),
            "percentile_rank_of_obs_%": float("nan"),
        }

    # 한 번의 순회로 평균과 percentile 계산 (O(n))
    total_sum = 0
    greater = 0
    for x in totals:
        total_sum += x
        if x > obs_total:
            greater += 1

    mean = total_sum / n

    # 두 번째 순회로 분산 계산 (O(n))
    var_sum = 0.0
    for x in totals:
        var_sum += (x - mean) ** 2

    std = (var_sum / (n - 1)) ** 0.5 if n > 1 else 0.0
    percentile = (greater / n) * 100.0

    return {
        "samples": int(n_sims),
        "obs_total_draws": int(obs_total),
        "mean_total_draws": float(mean),
        "std_total_draws": float(std),
        "percentile_rank_of_obs_%": float(percentile),
    }


# ---------- 파이프라인 ----------
def run_simulation(
    game_id: int,
    goal: int,
    obs_total: int,
    n_sims: int = N_SIMS,
    seed: int = None,  # None이면 자동 생성
    bins: int = BINS,
    # cdf: dict = {},
    # kv_store = None,  # Cloudflare KV 스토어 (선택적)
    precomputed_data = None  # 사전 계산된 데이터 (선택적)
) -> Tuple[Dict, str, Dict]:
    """시뮬레이션 실행 및 통계 분석

    Args:
        game_id: 게임 ID (1 또는 2)
        goal: 목표 획득 수
        obs_total: 관측된 총 뽑기 횟수
        n_sims: 시뮬레이션 횟수
        seed: 난수 시드 (None이면 시간 기반 자동 생성)
        bins: 히스토그램 bins (실제로는 내부에서 재계산됨)
        cdf: 사전 계산된 CDF (선택적)
        kv_store: Cloudflare KV 스토어 객체 (선택적)
        precomputed_data: 사전 계산된 압축 데이터 [min_val, freq] (선택적)

    Returns:
        (summary_dict, svg_string, timing_dict): 통계 요약, SVG 히스토그램, 타이밍 정보

    Raises:
        ValueError: 잘못된 입력값
    """
    import time
    timings = {}
    t_start = time.perf_counter()

    # 입력 검증
    t0 = time.perf_counter()
    cfg = GAME_TABLE.get(int(game_id))
    if not cfg:
        raise ValueError(f"Unknown GAME_ID: {game_id}")

    # 사전 계산된 데이터 필수
    if not precomputed_data:
        raise ValueError(f"No precomputed data available for game_id={game_id}, goal={goal}")
    timings["1_validation_ms"] = (time.perf_counter() - t0) * 1000

    # 데이터 압축 해제
    t1 = time.perf_counter()
    print(f"Using precomputed data for game_id={game_id}, goal={goal}")
    min_val, freq = precomputed_data
    totals = decompress_totals(min_val, freq)
    n_sims = len(totals)
    timings["2_decompress_ms"] = (time.perf_counter() - t1) * 1000

    # 실시간 시뮬레이션 비활성화 (코드 보존용)
    # if False:  # 실시간 시뮬레이션 (현재 비활성화)
    #     print(f"Running live simulation for game_id={game_id}, goal={goal}")
    #     if seed is None:
    #         import time
    #         seed = (int(time.time() * 1000000) ^ hash((game_id, goal, obs_total))) % (2**31)
    #     if not cdf:
    #         cdf = build_pity_cdf(game_id)
    #     totals = sample_total_draws(
    #         n_sims=n_sims,
    #         base_episodes=goal,
    #         cdf=cdf,
    #         ceil_ratio=cfg["CEIL_RATIO"],
    #         seed=seed,
    #     )

    # bins 계산: goal에 비례한 히스토그램 해상도 설정
    # 공식: goal * 160 / 3 (goal이 클수록 더 세밀한 bins)
    bins = (goal * 155) // 3

    # 통계 요약
    t2 = time.perf_counter()
    summary = summarize(totals, obs_total, n_sims)
    timings["3_summarize_ms"] = (time.perf_counter() - t2) * 1000

    # SVG 생성
    t3 = time.perf_counter()
    title = f"Total draws distribution: GET {goal} (n={n_sims})"
    svg = make_hist_svg(totals, obs_total, bins=bins, title=title)
    timings["4_svg_generation_ms"] = (time.perf_counter() - t3) * 1000

    # 명시적으로 totals 참조 해제 (메모리 절약)
    del totals

    timings["5_total_compute_ms"] = (time.perf_counter() - t_start) * 1000

    return summary, svg, timings
