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

# ----- fitting ------
from math import sqrt, pi, exp

def _mean(xs):  # 기존 정의 있어도 동일
    return (sum(xs) / len(xs)) if xs else float("nan")

def _std_mle(xs):  # MLE 표준편차(ddof=0) – 정규 최우추정치
    n = len(xs)
    if n <= 1:
        return 0.0
    mu = _mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / n
    return var ** 0.5

def _std_ddof1(xs):  # 이미 있으시면 이건 유지
    n = len(xs)
    if n <= 1:
        return 0.0
    mu = _mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / (n - 1)
    return var ** 0.5

def _normal_pdf(x, mu, sigma):
    if sigma <= 0:
        return 0.0
    z = (x - mu) / sigma
    return (1.0 / (sigma * sqrt(2.0 * pi))) * exp(-0.5 * z * z)

def _ecdf(xs_sorted, x):
    # 간단한 ECDF: P(X ≤ x)
    # xs_sorted는 사전 정렬 리스트
    lo, hi = 0, len(xs_sorted)
    while lo < hi:
        mid = (lo + hi) // 2
        if xs_sorted[mid] <= x:
            lo = mid + 1
        else:
            hi = mid
    return lo / len(xs_sorted)

def _ks_distance_to_normal(xs, mu, sigma, grid=200):
    # Kolmogorov–Smirnov D (간이): 균등 격자에서 sup|F_n - Φ|
    if not xs or sigma <= 0:
        return 1.0
    ys = sorted(xs)
    xmin, xmax = ys[0], ys[-1]
    if xmax == xmin:  # 단일값 보호
        xmax += 1.0
        xmin -= 1.0
    # 표준 정규 CDF 근사(에러펑션 없이 폴딩 근사): 빠른 Remez 계열 근사 사용
    # Hastings(1955) 근사에 기반한 간략 버전
    def phi(z):
        # Φ(z)
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
        if d > D: D = d
    return D

def make_hist_svg_with_normal(totals, obs_total, bins=128, title="", fit=True):
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
def build_pity_cdf(max_t: int, base_p: float, accel_start: int, accel_step: float) -> List[float]:
    """최초 성공까지 걸리는 시도수 T(1..max_t)의 CDF (list[float])"""
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
def _sample_T_from_cdf(cdf: List[float]) -> int:
    """cdf를 이용해 1..len(cdf) 범위의 T를 샘플링"""
    u = random.random()
    idx = bisect_left(cdf, u)
    return idx + 1  # 1-based 시도 횟수

def _binomial_7(p: float) -> int:
    """n=7, p의 이항 샘플(순수 파이썬)"""
    cnt = 0
    for _ in range(7):
        if random.random() < p:
            cnt += 1
    return cnt

def sample_total_draws(n_sims: int, base_episodes: int, cdf: List[float], ceil_ratio: float, seed: int) -> List[int]:
    """에피소드 수가 동적으로 늘어나는 구조를 반영해 각 시뮬레이션 총 뽑기수 리스트 반환."""
    random.seed(seed)
    totals: List[int] = [0] * n_sims
    for i in range(n_sims):
        add_ep = _binomial_7(ceil_ratio)   # 7번의 50% 시도 중 성공 수
        k = base_episodes + add_ep         # 실제 episode 수
        s = 0
        for _ in range(k):
            s += _sample_T_from_cdf(cdf)
        totals[i] = s
    return totals

# ---------- 요약 ----------
def _mean(xs: List[int]) -> float:
    return (sum(xs) / len(xs)) if xs else float("nan")

def _median(xs: List[int]) -> float:
    n = len(xs)
    if n == 0:
        return float("nan")
    ys = sorted(xs)
    mid = n // 2
    if n % 2 == 1:
        return float(ys[mid])
    return (ys[mid - 1] + ys[mid]) / 2.0

def _std_ddof1(xs: List[int]) -> float:
    n = len(xs)
    if n <= 1:
        return 0.0
    mu = _mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / (n - 1)
    return var ** 0.5

def summarize(totals: List[int], obs_total: int, n_sims: int) -> Dict:
    greater = sum(1 for x in totals if x > obs_total)
    percentile = (greater / len(totals) * 100.0) if totals else float("nan")
    return {
        "samples": int(n_sims),
        "obs_total_draws": int(obs_total),
        "mean_total_draws": float(_mean(totals)),
        "median_total_draws": float(_median(totals)),
        "std_total_draws": float(_std_ddof1(totals)),
        "percentile_rank_of_obs_%": float(percentile),
    }


# ---------- 파이프라인 ----------
def run_simulation(
    game_id: int,
    goal: int,
    obs_total: int,
    n_sims: int = 1_000_000,   # 순수 파이썬이라 기본값을 낮춤(필요시 조정)
    seed: int = 20251014,
    bins: int = 890,
) -> Tuple[Dict, str]:
    
    resp = {"Test key":"Test value"}
    svg = '<svg></svg>'
    return resp, svg

    cfg = GAME_TABLE.get(game_id)
    if not cfg:
        raise ValueError(f"Unknown GAME_ID: {game_id}")

    cdf = build_pity_cdf(
        max_t=cfg["MAX_T"],
        base_p=cfg["BASE_P"],
        accel_start=cfg["ACCEL_START"],
        accel_step=cfg["ACCEL_STEP"],
    )
    totals = sample_total_draws(
        n_sims=n_sims,
        base_episodes=goal,
        cdf=cdf,
        ceil_ratio=cfg["CEIL_RATIO"],
        seed=seed,
    )
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
    return summary, svg
