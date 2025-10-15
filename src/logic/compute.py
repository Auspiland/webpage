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

N_SIMS = 50_000  # 메모리 부담 감소 (100k → 50k)
SEED = 31014646
BINS = 300


# ----- fitting ------
from math import sqrt, pi, exp

# 통계 함수 (중복 정의 제거 - 여기서만 정의)
def _mean(xs):
    """평균 계산"""
    return (sum(xs) / len(xs)) if xs else float("nan")

def _std_mle(xs):
    """MLE 표준편차(ddof=0) – 정규 최우추정치"""
    n = len(xs)
    if n <= 1:
        return 0.0
    mu = _mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / n
    return var ** 0.5

def _std_ddof1(xs):
    """표본 표준편차(ddof=1) – 불편 추정량"""
    n = len(xs)
    if n <= 1:
        return 0.0
    mu = _mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / (n - 1)
    return var ** 0.5

def _normal_pdf(x, mu, sigma):
    """정규분포 확률밀도함수 (PDF)"""
    if sigma <= 0:
        return 0.0
    z = (x - mu) / sigma
    return (1.0 / (sigma * sqrt(2.0 * pi))) * exp(-0.5 * z * z)

def _ecdf(xs_sorted, x):
    """경험적 누적 분포 함수: P(X ≤ x)

    xs_sorted: 정렬된 데이터 리스트
    x: 평가할 값
    반환: 0~1 사이의 확률
    """
    # bisect_right와 동일한 로직 (순수 파이썬 구현 유지)
    lo, hi = 0, len(xs_sorted)
    while lo < hi:
        mid = (lo + hi) // 2
        if xs_sorted[mid] <= x:
            lo = mid + 1
        else:
            hi = mid
    return lo / len(xs_sorted)

def _ks_distance_to_normal(xs, mu, sigma, grid=100):
    """Kolmogorov-Smirnov 통계량: 데이터와 정규분포 간의 최대 차이

    Args:
        xs: 데이터 리스트
        mu: 정규분포 평균
        sigma: 정규분포 표준편차
        grid: 평가할 격자점 개수 (기본값 100으로 축소)

    Returns:
        KS 거리 (0~1), 값이 작을수록 정규분포에 가까움
    """
    if not xs or sigma <= 0:
        return 1.0
    ys = sorted(xs)
    xmin, xmax = ys[0], ys[-1]
    if xmax == xmin:  # 단일값 보호
        xmax += 1.0
        xmin -= 1.0

    # 표준 정규 CDF 근사 (Hastings 1955)
    def phi(z):
        """표준 정규분포의 누적분포함수 Φ(z)"""
        t = 1.0 / (1.0 + 0.2316419 * abs(z))
        b = ((((1.330274429 * t - 1.821255978) * t + 1.781477937) * t - 0.356563782) * t + 0.319381530) * t
        nd = (1.0 / sqrt(2.0 * pi)) * exp(-0.5 * z * z)
        val = 1.0 - nd * b
        return val if z >= 0 else 1.0 - val

    D = 0.0
    for i in range(grid + 1):
        x = xmin + (xmax - xmin) * i / grid
        Fn = _ecdf(ys, x)
        z = (x - mu) / sigma
        F = phi(z)
        d = abs(Fn - F)
        if d > D:
            D = d
    return D

def make_hist_svg_with_normal(totals, obs_total, bins=128, title="", fit=True):
    """히스토그램과 정규분포 적합을 SVG로 생성

    Args:
        totals: 시뮬레이션 데이터 리스트
        obs_total: 관측된 값 (빨간 수직선 표시)
        bins: 히스토그램 구간 수
        title: 차트 제목
        fit: 정규분포 곡선 표시 여부

    Returns:
        (svg_string, mu, sigma_mle, sigma_ddof1)
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

    # 정규 적합
    mu = _mean(totals)
    sigma_mle = _std_mle(totals)
    # 표시용 표준편차(표본 표준편차)도 계산해 summary에 같이 넣을 수 있게
    sigma_ddof1 = _std_ddof1(totals)

    # SVG 좌표
    W, H = 800, 450
    L, R, T, B = 60, 20, 30, 50
    innerW, innerH = W - L - R, H - T - B

    # 정규 PDF 샘플 (곡선)
    xs = []
    pdf = []
    if fit and sigma_mle > 0:
        pts = max(120, min(480, bins * 2))  # 매끄러운 곡선용 포인트
        for i in range(pts + 1):
            x = x_min + (x_max - x_min) * i / pts
            xs.append(x)
            pdf.append(_normal_pdf(x, mu, sigma_mle))

    # y 스케일(히스토 density와 정규 pdf를 같은 축에)
    y_max = max(max(density) if density else 1.0, max(pdf) if pdf else 0.0, 1e-6)

    def sx(x): return L + (x - x_min) * (innerW / max(1e-9, (x_max - x_min)))
    def sy(y): return T + innerH - y * (innerH / y_max)

    # 히스토 – 단일 path(면적; 기존보다 더 얇게)
    path_cmds = []
    x0 = edges[0]
    y0 = 0.0
    path_cmds.append(f"M {sx(x0):.2f} {sy(y0):.2f}")
    for i, d in enumerate(density):
        x1 = edges[i+1]
        if d < (y_max * 1e-5): d = 0.0
        path_cmds.append(f"L {sx(x1):.2f} {sy(y0):.2f}")
        path_cmds.append(f"L {sx(x1):.2f} {sy(d):.2f}")
        y0 = d
    path_cmds.append(f"L {sx(edges[-1]):.2f} {sy(0):.2f} Z")
    area_path = " ".join(path_cmds)

    # 정규 곡선 path
    curve = ""
    if pdf:
        parts = [f"M {sx(xs[0]):.2f} {sy(pdf[0]):.2f}"]
        for x, y in zip(xs[1:], pdf[1:]):
            parts.append(f"L {sx(x):.2f} {sy(y):.2f}")
        curve = f'<path d="{" ".join(parts)}" fill="none" stroke="#0d47a1" stroke-width="2.2"/>'

    # 관측치 수직선
    ox = sx(min(max(obs_total, x_min), x_max))
    obs_line = f'<line x1="{ox:.2f}" y1="{T}" x2="{ox:.2f}" y2="{T+innerH}" stroke="#c62828" stroke-dasharray="6 4" stroke-width="2"/>'

    # 축/레이블
    axes = [
        f'<line x1="{L}" y1="{T+innerH}" x2="{L+innerW}" y2="{T+innerH}" stroke="black"/>',
        f'<line x1="{L}" y1="{T}" x2="{L}" y2="{T+innerH}" stroke="black"/>',
        f'<text x="{L+innerW/2:.2f}" y="{H-8}" text-anchor="middle" font-size="12">Total draws</text>',
        f'<text x="16" y="{T+innerH/2:.2f}" transform="rotate(-90 16,{T+innerH/2:.2f})" font-size="12">Density</text>',
        f'<text x="{W/2:.2f}" y="20" text-anchor="middle" font-size="16">{title}</text>',
    ]
    ticks = []
    for i in range(6):
        vx = x_min + (x_max - x_min) * i / 5.0
        tx = sx(vx)
        ticks.append(f'<line x1="{tx:.2f}" y1="{T+innerH}" x2="{tx:.2f}" y2="{T+innerH+6}" stroke="black"/>')
        ticks.append(f'<text x="{tx:.2f}" y="{T+innerH+22}" text-anchor="middle" font-size="11">{int(round(vx))}</text>')

    legend = (
        f'<rect x="{W-280}" y="{T+8}" width="260" height="54" rx="8" fill="white" opacity="0.85" />'
        f'<circle cx="{W-260}" cy="{T+26}" r="5" fill="black" opacity="0.25"/><text x="{W-246}" y="{T+30}" font-size="12">Histogram (density)</text>'
        f'<line x1="{W-265}" y1="{T+44}" x2="{W-255}" y2="{T+44}" stroke="#0d47a1" stroke-width="2.2"/><text x="{W-246}" y="{T+48}" font-size="12">Normal fit PDF</text>'
    )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">
  <rect x="0" y="0" width="{W}" height="{H}" fill="white"/>
  {''.join(axes)}
  <path d="{area_path}" fill="black" opacity="0.14" stroke="none"/>
  {curve}
  {obs_line}
  {''.join(ticks)}
  {legend}
</svg>'''
    return svg, mu, sigma_mle, sigma_ddof1




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
    pmf = []
    prev = 0.0
    for x in cdf:
        pmf.append(x - prev)
        prev = x
    s = sum(pmf)
    if s <= 0:
        raise ValueError("Invalid CDF: sum must be positive")
    pmf = [p / s for p in pmf]

    M = len(pmf)
    scaled = [p * M for p in pmf]
    small, large = [], []
    for i, v in enumerate(scaled):
        (small if v < 1.0 else large).append(i)

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

    totals: List[int] = [0] * n_sims
    for i in range(n_sims):
        add_ep = _binomial_7(ceil_ratio)      # 추가 에피소드 수
        k = base_episodes + add_ep            # 총 에피소드 수
        s = 0
        for _ in range(k):
            s += _alias_sample(prob, alias)   # 각 에피소드의 뽑기 수
        totals[i] = s

    # 메모리 정리 (prob, alias는 로컬이므로 자동 해제됨)
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
    cfg = GAME_TABLE.get(game_id)
    if not cfg:
        raise ValueError(f"Unknown GAME_ID: {game_id}")

    if goal <= 0:
        raise ValueError(f"goal must be positive, got {goal}")

    if obs_total < 0:
        raise ValueError(f"obs_total must be non-negative, got {obs_total}")

    if n_sims <= 0:
        raise ValueError(f"n_sims must be positive, got {n_sims}")

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
    svg, mu, sigma_mle, sigma_ddof1 = make_hist_svg_with_normal(
        totals, obs_total, bins=bins, title=title, fit=True
    )
    # 간단 KS 거리(정규 적합 적합도 척도)
    ks = _ks_distance_to_normal(totals, mu, sigma_mle)
    summary.update({
        "normal_fit_mu": float(mu),
        "normal_fit_sigma_mle": float(sigma_mle),
        "normal_fit_sigma_sample": float(sigma_ddof1),
        "ks_distance": float(ks),
    })

    # 명시적으로 totals 참조 해제 (메모리 절약)
    del totals

    return summary, svg
