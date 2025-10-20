# -*- coding: utf-8 -*-
"""
run_simulation 메인 함수에서 사용하지 않는 함수들

이 파일은 시뮬레이션 생성, 데이터 압축/저장 등의 유틸리티 함수를 포함합니다.
"""
import random
from typing import List, Tuple
from bisect import bisect_left

# GAME_TABLE import (필요시)
from .compute import GAME_TABLE, N_SIMS, SEED


# ---------- 데이터 압축 ----------
def compress_totals(totals: List[int]) -> Tuple[int, List[int]]:
    """totals 리스트를 빈도 리스트로 압축 (무손실)

    Args:
        totals: 시뮬레이션 데이터 리스트 (100,000개)

    Returns:
        (min_value, freq_list):
        - min_value: 최소값
        - freq_list: 각 값의 빈도 [count_at_min, count_at_min+1, ...]
        예: goal=30 → 최대 30*160=4800개 원소
    """
    if not totals:
        return 0, []

    min_val = min(totals)
    max_val = max(totals)
    size = max_val - min_val + 1

    # 빈도 리스트 생성 (index = value - min_val)
    freq = [0] * size
    for v in totals:
        freq[v - min_val] += 1

    return min_val, freq


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


# ---------- 사전 계산 데이터 생성 ----------
def generate_precomputed_data(game_id: int, goal_range: range, n_sims: int = N_SIMS, seed: int = SEED):
    """goal 범위에 대해 시뮬레이션 실행 후 압축 데이터 생성

    Args:
        game_id: 게임 ID (1 또는 2)
        goal_range: goal 범위 (예: range(1, 21) → 1~20)
        n_sims: 시뮬레이션 횟수
        seed: 난수 시드

    Returns:
        2차원 리스트 구조:
        [
            [1, 2, 3, ..., 20],           # index 0: goal 리스트
            [min1, [freq1]],              # index 1: goal=1 압축 데이터
            [min2, [freq2]],              # index 2: goal=2 압축 데이터
            ...
            [min20, [freq20]]             # index 20: goal=20 압축 데이터
        ]
    """
    cfg = GAME_TABLE.get(int(game_id))
    if not cfg:
        raise ValueError(f"Unknown GAME_ID: {game_id}")

    # CDF는 한 번만 계산
    cdf = build_pity_cdf(game_id)

    # 결과 저장 구조
    result = [list(goal_range)]  # index 0: goal 리스트

    print(f"Starting simulation for game_id={game_id}, n_sims={n_sims:,}")

    for goal in goal_range:
        print(f"  Processing goal={goal}...", end=" ")

        # 시뮬레이션 실행
        totals = sample_total_draws(
            n_sims=n_sims,
            base_episodes=goal,
            cdf=cdf,
            ceil_ratio=cfg["CEIL_RATIO"],
            seed=seed + goal,  # goal마다 다른 시드
        )

        # 압축
        min_val, freq = compress_totals(totals)

        # 저장 (index = goal)
        result.append([min_val, freq])

        print(f"min={min_val}, freq_len={len(freq)}, compression={100*(1 - len(freq)/n_sims):.1f}%")

        # 메모리 해제
        del totals

    print("Simulation complete!")
    return result


def save_precomputed_data(data, filepath: str):
    """압축 데이터를 JSON 파일로 저장

    Args:
        data: generate_precomputed_data의 반환값
        filepath: 저장 경로 (예: "precomputed_game1.json")
    """
    import json
    with open(filepath, 'w') as f:
        json.dump(data, f)
    print(f"Saved to {filepath}")


def load_precomputed_data(filepath: str):
    """저장된 압축 데이터 불러오기

    Args:
        filepath: 파일 경로

    Returns:
        2차원 리스트 데이터
    """
    import json
    with open(filepath, 'r') as f:
        return json.load(f)


async def load_precomputed_from_assets(assets_binding, game_id: int, goal: int):
    """Assets에서 사전 계산된 압축 데이터 불러오기

    Args:
        assets_binding: Cloudflare Assets 바인딩 객체
        game_id: 게임 ID (1 또는 2)
        goal: 목표 획득 수

    Returns:
        압축된 시뮬레이션 데이터 [min_val, freq_list] 또는 None
    """
    import json
    from workers import Request

    # 정적 파일 경로
    asset_path = f"https://dummy/data/precomputed_game{game_id}_v2.json"

    try:
        # Assets에서 JSON 파일 가져오기 (~1-3ms)
        asset_req = Request(asset_path, method="GET")
        response = await assets_binding.fetch(asset_req)

        if response.status != 200:
            print(f"Asset not found: {asset_path}")
            return None

        # JSON 파싱
        full_data = await response.json()

        # 첫 번째 배열은 키 목록, 나머지는 데이터
        keys = full_data[0]

        # goal에 해당하는 인덱스 찾기
        if goal in keys:
            index = keys.index(goal) + 1  # +1은 keys 배열 다음부터 데이터
            return full_data[index]  # [min_val, freq_list]

        return None
    except Exception as e:
        print(f"Error loading from assets (game{game_id}_{goal}): {e}")
        return None


async def load_precomputed_from_kv(kv_store, game_id: int, goal: int):
    """KV에서 사전 계산된 압축 데이터 불러오기 (폴백)

    Args:
        kv_store: Cloudflare KV 스토어 객체
        game_id: 게임 ID (1 또는 2)
        goal: 목표 획득 수

    Returns:
        압축된 시뮬레이션 데이터 [min_val, freq_list] 또는 None
    """
    import json
    kv_key = f"game{game_id}_{goal}"

    try:
        data_str = await kv_store.get(kv_key)
        if data_str:
            return json.loads(data_str)
        return None
    except Exception as e:
        print(f"Error loading from KV ({kv_key}): {e}")
        return None
