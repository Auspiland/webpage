# -*- coding: utf-8 -*-
import random
from typing import Dict, Tuple, List, Sequence, Union
from math import sqrt, pi, exp, erf

# ---- GAME_ID별 기본 파라미터 ----
GAME_TABLE = {
    1: dict(CEIL_RATIO=0.5,  MAX_T=80, BASE_P=0.008, ACCEL_START=63, ACCEL_STEP=0.06),
    2: dict(CEIL_RATIO=0.55, MAX_T=90, BASE_P=0.006, ACCEL_START=73, ACCEL_STEP=0.06),
}

N_SIMS = 100_000
SEED = 31014646
BINS = 300


# ----- 통계 유틸리티 함수 ------
def _mean(xs: Sequence[Union[int, float]]) -> float:
    """샘플의 평균을 계산합니다."""
    return (sum(xs) / len(xs)) if xs else float("nan")

def _std_mle(xs: Sequence[Union[int, float]]) -> float:
    """MLE 표준편차(ddof=0) – 정규 최우추정치"""
    n = len(xs)
    if n <= 1:
        return 0.0
    mu = _mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / n
    return var ** 0.5

def _std_ddof1(xs: Sequence[Union[int, float]]) -> float:
    """불편 표준편차(ddof=1)를 계산합니다."""
    n = len(xs)
    if n <= 1:
        return 0.0
    mu = _mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / (n - 1)
    return var ** 0.5

def _median(xs: Sequence[Union[int, float]]) -> float:
    """샘플의 중앙값을 계산합니다."""
    n = len(xs)
    if n == 0:
        return float("nan")
    ys = sorted(xs)
    mid = n // 2
    if n % 2 == 1:
        return float(ys[mid])
    return (ys[mid - 1] + ys[mid]) / 2.0

def _normal_pdf(x: float, mu: float, sigma: float) -> float:
    """정규분포 PDF를 계산합니다."""
    if sigma <= 0:
        return 0.0
    z = (x - mu) / sigma
    return (1.0 / (sigma * sqrt(2.0 * pi))) * exp(-0.5 * z * z)

def _normal_cdf(z: float) -> float:
    """표준 정규분포 CDF를 계산합니다 (erf 사용)."""
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))

def _ecdf(xs_sorted: List[float], x: float) -> float:
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

def _ks_distance_to_normal(xs: Sequence[Union[int, float]], mu: float, sigma: float, grid: int = 200) -> float:
    """Kolmogorov-Smirnov D 통계량을 계산합니다 (균등 격자에서 sup|F_n - Φ|)."""
    if not xs or sigma <= 0:
        return 1.0
    ys = sorted(xs)
    xmin, xmax = ys[0], ys[-1]
    if xmax == xmin:  # 단일값 보호
        xmax += 1.0
        xmin -= 1.0

    D = 0.0
    for i in range(grid + 1):
        x = xmin + (xmax - xmin) * i / grid
        Fn = _ecdf(ys, x)
        z = (x - mu) / sigma
        F = _normal_cdf(z)
        d = abs(Fn - F)
        if d > D:
            D = d
    return D

def make_hist_svg_with_normal(
    totals: List[int],
    obs_total: int,
    bins: int = 128,
    title: str = "",
    fit: bool = True,
    show_hist: bool = True,
) -> Tuple[str, float, float, float, float, float, float]:
    """
    totals(원본 샘플 리스트)로 정규분포를 적합하고, SVG를 생성합니다.
    - show_hist=True: 히스토그램(밀도) 영역을 함께 표시
    - 항상 정규분포 곡선은 표시 (fit=True일 때 샘플 기반 적합)
    반환:
        (svg:str, mu:float, sigma_mle:float, sigma_ddof1:float,
         normal_pdf_at_obs:float, hist_density_at_obs:float, bin_width:float)
    """
    # ------------------------------
    # 히스토그램 구간 설정
    # ------------------------------
    x_min, x_max = min(totals), max(totals)
    if x_max == x_min:
        x_min -= 0.5
        x_max += 0.5
    bins = max(32, min(int(bins), 256))
    width = (x_max - x_min) / float(bins)
    edges = [x_min + i * width for i in range(bins + 1)]
    counts = [0] * bins
    for v in totals:
        i = int((v - x_min) / width)
        if i == bins:
            i -= 1
        counts[i] += 1
    n = len(totals)
    density = [c / (n * width) for c in counts]  # 히스토그램 밀도

    # ------------------------------
    # 정규 적합 (항상 수행)
    # ------------------------------
    mu = _mean(totals)
    sigma_mle = _std_mle(totals)
    sigma_ddof1 = _std_ddof1(totals)

    # obs 위치의 값들 (정규 pdf, 히스토그램 밀도)
    normal_pdf_at_obs = _normal_pdf(obs_total, mu, sigma_mle) if sigma_mle > 0 else float("nan")
    if obs_total < x_min or obs_total > x_max:
        hist_density_at_obs = 0.0
        obs_bin_idx = None
    else:
        obs_bin_idx = int((obs_total - x_min) / width)
        if obs_bin_idx == bins:
            obs_bin_idx -= 1
        hist_density_at_obs = density[obs_bin_idx]

    # ------------------------------
    # SVG 좌표/레이아웃
    # ------------------------------
    W, H = 800, 450
    L, R, T, B = 60, 20, 30, 50
    innerW, innerH = W - L - R, H - T - B

    def sx(x):
        span = max(1e-9, (x_max - x_min))
        return L + (x - x_min) * (innerW / span)

    def sy(y):
        return T + innerH - y * (innerH / y_max)

    # ------------------------------
    # 정규 PDF 곡선 좌표
    # ------------------------------
    xs, pdf = [], []
    if fit and sigma_mle > 0:
        pts = max(120, min(480, bins * 2))
        for i in range(pts + 1):
            x = x_min + (x_max - x_min) * i / pts
            xs.append(x)
            pdf.append(_normal_pdf(x, mu, sigma_mle))

    # y 스케일 (히스토그램/정규 곡선 동시 고려)
    y_max_candidates = [1e-6]
    if pdf:
        y_max_candidates.append(max(pdf))
    if show_hist and density:
        y_max_candidates.append(max(density))
    y_max = max(y_max_candidates)

    # ------------------------------
    # 히스토그램 path (옵션)
    # ------------------------------
    area_path = ""
    if show_hist:
        path_cmds = []
        x0 = edges[0]
        y0 = 0.0
        path_cmds.append(f"M {sx(x0):.2f} {sy(y0):.2f}")
        for i, d in enumerate(density):
            x1 = edges[i + 1]
            if d < (y_max * 1e-5):
                d = 0.0
            path_cmds.append(f"L {sx(x1):.2f} {sy(y0):.2f}")
            path_cmds.append(f"L {sx(x1):.2f} {sy(d):.2f}")
            y0 = d
        path_cmds.append(f"L {sx(edges[-1]):.2f} {sy(0):.2f} Z")
        area_path = f'<path d="{" ".join(path_cmds)}" fill="black" opacity="0.14" stroke="none"/>'

    # ------------------------------
    # 정규 곡선 path
    # ------------------------------
    curve = ""
    if pdf:
        parts = [f"M {sx(xs[0]):.2f} {sy(pdf[0]):.2f}"]
        for x, y in zip(xs[1:], pdf[1:]):
            parts.append(f"L {sx(x):.2f} {sy(y):.2f}")
        curve = f'<path d="{" ".join(parts)}" fill="none" stroke="#0d47a1" stroke-width="2.2"/>'

    # ------------------------------
    # 관측치 수직선
    # ------------------------------
    ox = sx(min(max(obs_total, x_min), x_max))
    obs_line = (
        f'<line x1="{ox:.2f}" y1="{T}" x2="{ox:.2f}" y2="{T + innerH}" '
        f'stroke="#c62828" stroke-dasharray="6 4" stroke-width="2"/>'
    )

    # ------------------------------
    # 축/레이블/눈금/범례
    # ------------------------------
    axes = [
        f'<line x1="{L}" y1="{T + innerH}" x2="{L + innerW}" y2="{T + innerH}" stroke="black"/>',
        f'<line x1="{L}" y1="{T}" x2="{L}" y2="{T + innerH}" stroke="black"/>',
        f'<text x="{L + innerW / 2:.2f}" y="{H - 8}" text-anchor="middle" font-size="12">Total draws</text>',
        f'<text x="16" y="{T + innerH / 2:.2f}" transform="rotate(-90 16,{T + innerH / 2:.2f})" font-size="12">Density</text>',
        f'<text x="{W / 2:.2f}" y="20" text-anchor="middle" font-size="16">{title}</text>',
    ]
    ticks = []
    for i in range(6):
        vx = x_min + (x_max - x_min) * i / 5.0
        tx = sx(vx)
        ticks.append(f'<line x1="{tx:.2f}" y1="{T + innerH}" x2="{tx:.2f}" y2="{T + innerH + 6}" stroke="black"/>')
        ticks.append(
            f'<text x="{tx:.2f}" y="{T + innerH + 22}" text-anchor="middle" font-size="11">{int(round(vx))}</text>'
        )

    legend_items = []
    if show_hist:
        legend_items.append(
            f'<circle cx="{W - 260}" cy="{T + 26}" r="5" fill="black" opacity="0.25"/>'
            f'<text x="{W - 246}" y="{T + 30}" font-size="12">Histogram (density)</text>'
        )
    legend_items.append(
        f'<line x1="{W - 265}" y1="{T + 44}" x2="{W - 255}" y2="{T + 44}" stroke="#0d47a1" stroke-width="2.2"/>'
        f'<text x="{W - 246}" y="{T + 48}" font-size="12">Normal fit PDF</text>'
    )
    legend_height = 54 if show_hist else 36
    legend = (
        f'<rect x="{W - 280}" y="{T + 8}" width="260" height="{legend_height}" rx="8" fill="white" opacity="0.85" />'
        + "".join(legend_items)
    )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">
  <rect x="0" y="0" width="{W}" height="{H}" fill="white"/>
  {''.join(axes)}
  {area_path}
  {curve}
  {obs_line}
  {''.join(ticks)}
  {legend}
</svg>'''

    return (
        svg,
        float(mu),
        float(sigma_mle),
        float(sigma_ddof1),
        float(normal_pdf_at_obs),
        float(hist_density_at_obs),
        float(width),
    )


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

# ---------- 난수/샘플 (Alias Method) ----------
def _build_alias_from_cdf(cdf: List[float]) -> Tuple[List[float], List[int]]:
    pmf = []
    prev = 0.0
    for x in cdf:
        pmf.append(x - prev)
        prev = x
    s = sum(pmf)
    if s <= 0:
        raise ValueError("Invalid CDF")
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
    """Alias 샘플링 (O(1))으로 1..M 범위의 값을 반환합니다."""
    i = int(random.random() * len(prob))   # 0..M-1
    return (i + 1) if random.random() < prob[i] else (alias[i] + 1)

def _binomial_7(p: float) -> int:
    """Binomial(7, p) 분포에서 샘플링합니다."""
    c = 0
    for _ in range(7):
        if random.random() < p:
            c += 1
    return c

def sample_total_draws(n_sims: int, base_episodes: int,
                       cdf: List[float], ceil_ratio: float, seed: int) -> List[int]:
    """에피소드 수가 동적으로 늘어나는 구조를 반영해 각 시뮬레이션 총 뽑기수 리스트를 반환합니다."""
    random.seed(seed)
    prob, alias = _build_alias_from_cdf(cdf)  # O(M) 1회 전처리

    totals: List[int] = [0] * n_sims
    for i in range(n_sims):
        add_ep = _binomial_7(ceil_ratio)      # O(1)
        k = base_episodes + add_ep
        s = 0
        for _ in range(k):                    # 각 샘플 O(1)
            s += _alias_sample(prob, alias)
        totals[i] = s
    return totals

# ---------- 요약 ----------
def summarize(totals: List[int], obs_total: int, n_sims: int) -> Dict:
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
    seed: int = SEED,
    bins: int = BINS,
    show_hist: bool = False,
    cdf: dict = {}
) -> Tuple[Dict, str]:
    """
    몬테카르로 시뮬레이션을 실행하고 결과를 반환합니다.

    Args:
        game_id: 게임 ID (1 또는 2)
        goal: 목표 에피소드 수
        obs_total: 관측된 총 뽑기 수
        n_sims: 시뮬레이션 횟수
        seed: 난수 시드
        bins: 히스토그램 bin 수
        show_hist: 히스토그램 표시 여부
        cdf: 사전 계산된 CDF (선택사항)

    Returns:
        (summary, svg): 요약 통계와 SVG 그래프
    """
    # 입력 검증
    cfg = GAME_TABLE.get(game_id)
    if not cfg:
        raise ValueError(f"Unknown GAME_ID: {game_id}")

    if goal <= 0:
        raise ValueError(f"goal must be positive, got {goal}")

    if obs_total <= 0:
        raise ValueError(f"obs_total must be positive, got {obs_total}")

    if n_sims <= 0:
        raise ValueError(f"n_sims must be positive, got {n_sims}")

    if bins <= 0:
        raise ValueError(f"bins must be positive, got {bins}")

    if not cdf:
        cdf = build_pity_cdf(game_id)

    totals = sample_total_draws(
        n_sims=n_sims,
        base_episodes=goal,
        cdf=cdf,
        ceil_ratio=cfg["CEIL_RATIO"],
        seed=seed,
    )

    # obs 관련 계산만 수행
    summary = summarize(totals, obs_total, n_sims)

    return summary, ""
