#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
기존 데이터를 0부터 시작하는 형식으로 변환
"""
import json

def convert_precomputed_data(input_file, output_file):
    """기존 [min_val, freq] 형식을 0부터 시작하는 freq로 변환"""
    with open(input_file, 'r') as f:
        data = json.load(f)

    # data[0]은 goal 리스트 그대로 유지
    result = [data[0]]

    # data[1~20]은 [min_val, freq] → freq_from_zero로 변환
    for i in range(1, len(data)):
        min_val, freq = data[i]

        # 0부터 시작하는 빈도 리스트 생성
        max_val = min_val + len(freq) - 1
        freq_from_zero = [0] * (max_val + 1)

        # min_val부터 채우기
        for j, count in enumerate(freq):
            freq_from_zero[min_val + j] = count

        result.append(freq_from_zero)

    with open(output_file, 'w') as f:
        json.dump(result, f)

    print(f"Converted {input_file} -> {output_file}")
    print(f"  Original format: [min_val, freq]")
    print(f"  New format: freq (0-indexed)")

if __name__ == "__main__":
    convert_precomputed_data("precomputed_game1.json", "precomputed_game1_v2.json")
    convert_precomputed_data("precomputed_game2.json", "precomputed_game2_v2.json")
    print("\nConversion complete!")
