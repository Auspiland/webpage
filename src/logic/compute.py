# -*- coding: utf-8 -*-
import math
import json
import numpy as np
from typing import Dict, Tuple

# ---- 기본 파라미터 맵 (GAME_ID별) ----
GAME_TABLE = {
    1: dict(CEIL_RATIO=0.5,  MAX_T=80, BASE_P=0.008, ACCEL_START=63, ACCEL_STEP=0.06),
    2: dict(CEIL_RATIO=0.55, MAX_T=90, BASE_P=0.006, ACCEL_START=73, ACCEL_STEP=0.06),
}

def build_pity_cdf(max_t: int, base_p: float, accel_start: int, accel_step: float) -> np.ndarray:
    """최초 성공까지 걸리는 시도수 T(1..max_t)의 CDF."""
    p = np.empty(max_t, dtype=np.float64)
    for t in range(1, max_t + 1):
        p[t-1] = base_p if t <= accel_start else min(base_p + accel_step * (t - accel_start), 1.0)

    pmf = np.empty(max_t, dtype=np.float64)
    survival = 1.0
    for i in range(max_t):
        pmf[i] = survival * p[i]
        survival *= (1.0 - p[i])

    cdf = np.cumsum(pmf)
    tail = 1.0 - cdf[-1]
    if tail > 0:
        pmf[-1] += tail
        cdf = np.cumsum(pmf)
    return cdf

def sample_total_draws(n_sims: int, base_episodes: int, cdf: np.ndarray, ceil_ratio: float, seed: int) -> np.ndarray:
    """에피소드 수가 동적으로 늘어나는 구조(7개의 50% 시도 가정)를 반영해 각 시뮬레이션의 총 뽑기수를 샘플링."""
    rng = np.random.default_rng(seed)
    add_episodes = rng.binomial(n=7, p=ceil_ratio, size=n_sims)  # “절반 성공시 에피소드 +1” 모델
    episodes_each = base_episodes + add_episodes

    totals = np.empty(n_sims, dtype=np.int64)
    unique_ep = np.unique(episodes_each)
    for k in unique_ep:
        idx = np.where(episodes_each == k)[0]
        if k <= 0:
            totals[idx] = 0
            continue
        U = rng.random((idx.size, k), dtype=np.float32)
        T_block = np.searchsorted(cdf, U, side="left") + 1  # (m, k)
        totals[idx] = T_block.sum(axis=1, dtype=np.int64)
    return totals

def summarize(totals: np.ndarray, obs_total: int, n_sims: int) -> Dict:
    """요약 통계 생성 (pandas 없이)."""
    # 문제 정의상: 관측치보다 “큰” 쪽 꼬리
    percentile = float((totals > obs_total).mean() * 100.0)
    mean = float(totals.mean()) if totals.size else float("nan")
    median = float(np.median(totals)) if totals.size else float("nan")
    # 표본표준편차(ddof=1) - 표본크기가 1이면 NaN 방지
    if totals.size > 1:
        std = float(totals.std(ddof=1))
    else:
        std = 0.0
    return {
        "samples": int(n_sims),
        "obs_total_draws": int(obs_total),
        "mean_total_draws": mean,
        "median_total_draws": median,
        "std_total_draws": std,
        "percentile_rank_of_obs_%": percentile,
    }

# ---------- 간단 SVG 생성기 (히스토그램 + 관측치 라인) ----------
def _svg_rect(x, y, w, h) -> str:
    return f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="black" opacity="0.12"/>'

def _svg_line(x1, y1, x2, y2, dashed=False, label=None) -> str:
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    text = ""
    if label:
        text = f'<text x="{x2+6:.2f}" y="{y2-6:.2f}" font-size="12" fill="black">{label}</text>'
    return f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="black"{dash} stroke-width="2"/>{text}'

def make_hist_svg(totals: np.ndarray, obs_total: int, bins: int, title: str = "") -> str:
    """matplotlib 없이 SVG 히스토그램 생성 (density=True)."""
    if totals.size == 0:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450"></svg>'

    counts, edges = np.histogram(totals, bins=bins, density=True)
    # 캔버스
    W, H = 800, 450
    L, R, T, B = 60, 20, 30, 50
    innerW, innerH = W - L - R, H - T - B

    # 스케일
    x_min, x_max = edges[0], edges[-1]
    y_max = float(max(counts) if counts.size else 1.0)

    def sx(x):  # data x -> svg
        return L + (x - x_min) * (innerW / max(1e-9, (x_max - x_min)))
    def sy(y):  # density y -> svg
        return T + innerH - y * (innerH / max(1e-9, y_max))

    # 히스토그램 바
    bars = []
    for c, x0, x1 in zip(counts, edges[:-1], edges[1:]):
        if c <= 0: 
            continue
        x = sx(x0)
        w = max(0.6, sx(x1) - sx(x0))
        y = sy(c)
        h = (T + innerH) - y
        bars.append(_svg_rect(x, y, w, h))

    # 관측치 수직선
    ox = sx(min(max(obs_total, x_min), x_max))
    line = _svg_line(ox, T, ox, T + innerH, dashed=True, label=str(obs_total))

    # 축/라벨
    axes = [
        f'<line x1="{L}" y1="{T+innerH}" x2="{L+innerW}" y2="{T+innerH}" stroke="black"/>',  # x-axis
        f'<line x1="{L}" y1="{T}" x2="{L}" y2="{T+innerH}" stroke="black"/>',                 # y-axis
        f'<text x="{L+innerW/2:.2f}" y="{H-8}" text-anchor="middle" font-size="12">Total draws</text>',
        f'<text x="16" y="{T+innerH/2:.2f}" transform="rotate(-90 16,{T+innerH/2:.2f})" font-size="12">Density</text>',
        f'<text x="{W/2:.2f}" y="20" text-anchor="middle" font-size="16">{title}</text>',
    ]

    # 간단 x축 눈금 6개
    ticks = []
    for i in range(6):
        vx = x_min + (x_max - x_min) * i / 5.0
        tx = sx(vx)
        ticks.append(f'<line x1="{tx:.2f}" y1="{T+innerH}" x2="{tx:.2f}" y2="{T+innerH+6}" stroke="black"/>')
        ticks.append(f'<text x="{tx:.2f}" y="{T+innerH+22}" text-anchor="middle" font-size="11">{int(round(vx))}</text>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">
  <rect x="0" y="0" width="{W}" height="{H}" fill="white"/>
  {''.join(axes)}
  {''.join(bars)}
  {line}
  {''.join(ticks)}
</svg>'''
    return svg

def run_simulation(
    game_id: int,
    goal: int,
    obs_total: int,
    n_sims: int = 10_000_000,  # Workers CPU 제약 고려(필요시 조정)
    seed: int = 20251014,
    bins: int = 900
) -> Tuple[Dict, str]:
    """시뮬레이션 요약(JSON)과 히스토그램 SVG 문자열 반환."""
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
        seed=seed
    )
    summary = summarize(totals, obs_total, n_sims)
    title = f"Total draws distribution: GET {goal} (n={n_sims})"
    svg = make_hist_svg(totals, obs_total, bins=bins, title=title)
    return summary, svg
