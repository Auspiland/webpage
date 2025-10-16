# -*- coding: utf-8 -*-
import random
from bisect import bisect_left
from math import isfinite
from typing import Dict, Tuple, List

# ---- GAME_ID별 기본 파라미터 ----
GAME_TABLE = {
    1: dict(CEIL_RATIO=0.5,  MAX_T=80, BASE_P=0.008, ACCEL_START=63, ACCEL_STEP=0.06),
    2: dict(CEIL_RATIO=0.55, MAX_T=90, BASE_P=0.006, ACCEL_START=73, ACCEL_STEP=0.06),
}

N_SIMS = 100_000  # 메모리 부담 감소 (100k → 50k)
SEED = 31014646
BINS = 300


# ----- 최소한의 통계 함수만 유지 ------
from math import sqrt

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




# ---------- CDF 구성 ----------
def build_pity_cdf(game_id) -> List[float]:
    """최초 성공까지 걸리는 시도수 T(1..max_t)의 CDF (list[float])"""
    cfg = GAME_TABLE.get(game_id)
    max_t = cfg["MAX_T"]
    base_p = cfg["BASE_P"]
    accel_start = cfg["ACCEL_START"]
    accel_step = cfg["ACCEL_STEP"]

    # p[t-1] = 각 시도에서의 성공 확률
    p = [0.0] * max_t
    for t in range(1, max_t + 1):
        if t <= accel_start:
            p[t-1] = base_p
        else:
            inc = base_p + accel_step * (t - accel_start)
            p[t-1] = inc if inc < 1.0 else 1.0

    pmf = [0.0] * max_t
    survival = 1.0
    for i in range(max_t):
        pmf[i] = survival * p[i]
        survival *= (1.0 - p[i])

    cdf = [0.0] * max_t
    s = 0.0
    for i in range(max_t):
        s += pmf[i]
        cdf[i] = s

    # 꼬리 보정
    tail = 1.0 - cdf[-1]
    if tail > 0:
        pmf[-1] += tail
        s = 0.0
        for i in range(max_t):
            s += pmf[i]
            cdf[i] = s
    return cdf

# ---------- 난수/샘플 ----------

def _build_alias_from_cdf(cdf: List[float]) -> Tuple[List[float], List[int]]:
    """Walker's Alias Method를 위한 전처리 테이블 생성

    CDF에서 PMF를 추출하고 O(1) 샘플링을 위한 alias 테이블 구성

    Args:
        cdf: 누적분포함수 (정규화되지 않아도 됨)

    Returns:
        (prob, alias): Alias Method용 확률 테이블과 별칭 테이블
    """
    # 리스트 컴프리헨션으로 PMF 추출 (최적화)
    M = len(cdf)
    pmf = [cdf[0]] + [cdf[i] - cdf[i-1] for i in range(1, M)]
    s = sum(pmf)
    if s <= 0:
        raise ValueError("Invalid CDF: sum must be positive")

    # 정규화 및 스케일링을 한 번에 처리
    scaled = [p * M / s for p in pmf]

    # 초기 분류
    small = [i for i, v in enumerate(scaled) if v < 1.0]
    large = [i for i, v in enumerate(scaled) if v >= 1.0]

    prob = [0.0] * M
    alias = [0] * M

    while small and large:
        s_i = small.pop()
        l_i = large.pop()
        prob[s_i] = scaled[s_i]
        alias[s_i] = l_i
        scaled[l_i] = scaled[l_i] + scaled[s_i] - 1.0
        (small if scaled[l_i] < 1.0 else large).append(l_i)

    for i in large + small:
        prob[i] = 1.0
    return prob, alias

def _alias_sample(prob: List[float], alias: List[int]) -> int:
    """Alias Method를 이용한 O(1) 샘플링

    Returns:
        1부터 len(prob)까지의 정수 (1-indexed)
    """
    i = int(random.random() * len(prob))
    return (i + 1) if random.random() < prob[i] else (alias[i] + 1)

def _binomial_7(p: float) -> int:
    """이항분포 B(7, p) 샘플링

    Args:
        p: 성공 확률

    Returns:
        0~7 사이의 성공 횟수
    """
    c = 0
    for _ in range(7):
        if random.random() < p:
            c += 1
    return c

def sample_total_draws(n_sims: int, base_episodes: int,
                       cdf: List[float], ceil_ratio: float, seed: int) -> List[int]:
    """몬테카를로 시뮬레이션: 총 뽑기 횟수 분포 생성

    Args:
        n_sims: 시뮬레이션 반복 횟수
        base_episodes: 기본 에피소드 수
        cdf: 단일 에피소드의 CDF
        ceil_ratio: 추가 에피소드 발생 확률
        seed: 난수 시드

    Returns:
        각 시뮬레이션의 총 뽑기 횟수 리스트
    """
    # 난수 생성기 초기화 (전역 상태 사용)
    random.seed(seed)

    # Alias 테이블 전처리
    prob, alias = _build_alias_from_cdf(cdf)

    # 로컬 변수로 함수 참조 캐싱 (속도 향상)
    _rand = random.random
    M = len(prob)

    totals: List[int] = [0] * n_sims
    for i in range(n_sims):
        # 이항분포 인라인 (함수 호출 오버헤드 제거)
        add_ep = sum(1 for _ in range(7) if _rand() < ceil_ratio)
        k = base_episodes + add_ep

        # Alias 샘플링 인라인 (최적화)
        s = 0
        for _ in range(k):
            idx = int(_rand() * M)
            s += (idx + 1) if _rand() < prob[idx] else (alias[idx] + 1)
        totals[i] = s

    return totals

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
    cdf: dict = {}
) -> Tuple[Dict, str]:
    """시뮬레이션 실행 및 통계 분석

    Args:
        game_id: 게임 ID (1 또는 2)
        goal: 목표 획득 수
        obs_total: 관측된 총 뽑기 횟수
        n_sims: 시뮬레이션 횟수
        seed: 난수 시드 (None이면 시간 기반 자동 생성)
        bins: 히스토그램 bins (실제로는 내부에서 재계산됨)
        cdf: 사전 계산된 CDF (선택적)

    Returns:
        (summary_dict, svg_string): 통계 요약과 SVG 히스토그램

    Raises:
        ValueError: 잘못된 입력값
    """
    # 입력 검증
    cfg = GAME_TABLE.get(int(game_id))
    if not cfg:
        raise ValueError(f"Unknown GAME_ID: {game_id}")

    # seed가 None이면 각 호출마다 다른 시드 생성
    if seed is None:
        import time
        seed = (int(time.time() * 1000000) ^ hash((game_id, goal, obs_total))) % (2**31)

    if not cdf:
        cdf = build_pity_cdf(game_id)
    
    totals = sample_total_draws(
        n_sims=n_sims,
        base_episodes=goal,
        cdf=cdf,
        ceil_ratio=cfg["CEIL_RATIO"],
        seed=seed,
    )
    # bins 계산: goal에 비례한 히스토그램 해상도 설정
    # 공식: goal * 160 / 3 (goal이 클수록 더 세밀한 bins)
    bins = (goal * 155) // 3

    summary = summarize(totals, obs_total, n_sims)
    title = f"Total draws distribution: GET {goal} (n={n_sims})"
    svg = make_hist_svg(totals, obs_total, bins=bins, title=title)

    # 명시적으로 totals 참조 해제 (메모리 절약)
    del totals

    return summary, svg
