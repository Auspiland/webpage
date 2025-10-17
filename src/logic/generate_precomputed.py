#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
사전 계산 데이터 생성 스크립트
goal 1~20에 대해 1,000,000 시뮬레이션 실행 후 압축 데이터 저장
"""

from compute import generate_precomputed_data, save_precomputed_data

if __name__ == "__main__":
    # Game ID 1에 대해 데이터 생성
    print("=" * 60)
    print("Generating precomputed data for GAME_ID=1")
    print("=" * 60)

    data_game1 = generate_precomputed_data(
        game_id=1,
        goal_range=range(1, 21),  # 1~20
        n_sims=1_000_000
    )

    save_precomputed_data(data_game1, "precomputed_game1.json")

    print("\n" + "=" * 60)
    print("Generating precomputed data for GAME_ID=2")
    print("=" * 60)

    # Game ID 2에 대해 데이터 생성
    data_game2 = generate_precomputed_data(
        game_id=2,
        goal_range=range(1, 21),  # 1~20
        n_sims=1_000_000
    )

    save_precomputed_data(data_game2, "precomputed_game2.json")

    print("\n" + "=" * 60)
    print("All data generation complete!")
    print("=" * 60)
