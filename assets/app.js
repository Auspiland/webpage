(() => {
  const form = document.getElementById("f");
  const summaryEl = document.getElementById("summary");
  const plotEl = document.getElementById("plot");

  const btnReset = document.getElementById("btnReset");
  const btnDlSvg = document.getElementById("btnDownloadSvg");
  const btnDlJson = document.getElementById("btnDownloadJson");

  const rateMeta = document.getElementById("rateMeta");
  const rlLimit = document.getElementById("rlLimit");
  const rlRemain = document.getElementById("rlRemain");
  const rlReset = document.getElementById("rlReset");

  const descriptionModal = document.getElementById("descriptionModal");
  const modalTitle = document.getElementById("modalTitle");
  const modalDescription = document.getElementById("modalDescription");
  const closeModalBtn = document.getElementById("closeModal");

  let lastSvgText = null;
  let lastSummary = null;

  // 항목별 한국어 이름과 설명
  const summaryMetadata = {
    "samples": {
      label: "시뮬레이션 샘플 수",
      description: "시뮬레이션을 수행한 총 횟수입니다.",
      isBasic: false
    },
    "obs_total_draws": {
      label: "관측 총 뽑기수",
      description: "실제로 관측된 총 뽑기(드로) 횟수입니다.",
      isBasic: false
    },
    "mean_total_draws": {
      label: "시뮬레이션 평균",
      description: "시뮬레이션 결과 totals의 산술평균입니다.",
      isBasic: true
    },
    "median_total_draws": {
      label: "시뮬레이션 중앙값",
      description: "시뮬레이션 결과 totals의 중앙값입니다.",
      isBasic: false
    },
    "std_total_draws": {
      label: "표본 표준편차",
      description: "시뮬레이션 결과의 표본 표준편차(ddof=1)입니다.",
      isBasic: true
    },
    "percentile_rank_of_obs_%": {
      label: "관측 상위비율(%)",
      description: "관측값이 샘플 중 상위 몇 % 꼬리(우측 꼬리)에 속하는지입니다. (P(X>obs)×100)",
      isBasic: true
    },
    "normal_fit_mu": {
      label: "정규 적합 평균 μ",
      description: "원본 totals에 정규분포를 적합했을 때의 평균(모수)입니다.",
      isBasic: false
    },
    "normal_fit_sigma_mle": {
      label: "정규 적합 표준편차 σ(MLE)",
      description: "정규 적합의 표준편차(MLE, 분모 n)입니다.",
      isBasic: false
    },
    "normal_fit_sigma_sample": {
      label: "표본 표준편차(ddof=1)",
      description: "참고용 표본 표준편차(분모 n-1)입니다.",
      isBasic: false
    },
    "ks_distance": {
      label: "KS 거리",
      description: "경험적 분포와 정규 적합 분포 간 Kolmogorov-Smirnov 거리(작을수록 적합).",
      isBasic: false
    },
    "normal_pdf_at_obs": {
      label: "정규 PDF@관측값",
      description: "적합된 정규분포 N(μ,σ²)에서 obs_total의 확률밀도값입니다(누적 아님).",
      isBasic: false
    },
    "hist_density_at_obs": {
      label: "히스토 밀도@관측값",
      description: "동일 지점에서의 히스토그램 기반 경험적 밀도 추정값입니다.",
      isBasic: false
    },
    "hist_bin_width": {
      label: "히스토 bin 폭",
      description: "히스토그램 구간 너비입니다(밀도×bin폭 ≈ 해당 구간 확률질량).",
      isBasic: false
    },
    "theoretical_percentile": {
      label: "정규 이론 꼬리확률(%)",
      description: "적합 정규분포 기준 ((1-Φ((obs-μ)/σ))×100). 경험치(percentile_rank_of_obs_%)와 비교용.",
      isBasic: true
    }
  };

  // 모달 열기
  function openDescriptionModal(key) {
    const meta = summaryMetadata[key];
    if (!meta) return;

    modalTitle.textContent = meta.label;
    modalDescription.textContent = meta.description;
    descriptionModal.classList.add("active");
  }

  // 모달 닫기
  function closeDescriptionModal() {
    descriptionModal.classList.remove("active");
  }

  closeModalBtn.addEventListener("click", closeDescriptionModal);
  descriptionModal.addEventListener("click", (e) => {
    if (e.target === descriptionModal) closeDescriptionModal();
  });

  let isExpanded = false;

  // summary를 테이블로 렌더링 (기본/확장 모드)
  function renderSummary(summary, expanded = false) {
    summaryEl.innerHTML = "";

    // 토글 버튼
    const toggleBtn = document.createElement("button");
    toggleBtn.textContent = expanded ? "▼ 요약 보기" : "▶ 전체 보기";
    toggleBtn.className = "toggle-btn";
    toggleBtn.addEventListener("click", () => {
      isExpanded = !isExpanded;
      renderSummary(summary, isExpanded);
    });

    // 테이블 생성
    const table = document.createElement("table");
    table.className = "summary-table";

    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    const th1 = document.createElement("th");
    th1.textContent = "항목";
    const th2 = document.createElement("th");
    th2.textContent = "값";
    headerRow.appendChild(th1);
    headerRow.appendChild(th2);
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");

    for (const [key, value] of Object.entries(summary)) {
      const meta = summaryMetadata[key];
      if (!meta) continue;

      // 기본 모드: isBasic=true 항목만 표시
      // 확장 모드: samples, obs_total_draws 제외하고 모두 표시
      if (!expanded && !meta.isBasic) continue;
      if (expanded && (key === "samples" || key === "obs_total_draws")) continue;

      const row = document.createElement("tr");

      const labelCell = document.createElement("td");
      labelCell.className = "summary-label";
      labelCell.textContent = meta.label;
      labelCell.style.cursor = "pointer";
      labelCell.addEventListener("click", () => openDescriptionModal(key));

      const valueCell = document.createElement("td");
      valueCell.className = "summary-value";

      // 값 포맷팅
      if (typeof value === "number") {
        valueCell.textContent = value.toLocaleString("ko-KR", {
          maximumFractionDigits: 5
        });
      } else {
        valueCell.textContent = String(value);
      }

      row.appendChild(labelCell);
      row.appendChild(valueCell);
      tbody.appendChild(row);
    }

    table.appendChild(tbody);
    summaryEl.appendChild(toggleBtn);
    summaryEl.appendChild(table);
  }

  function readForm(f) {
    const fd = new FormData(f);
    const obj = {};
    for (const [k, v] of fd.entries()) obj[k] = v;
    ["GAME_ID","GOAL","OBS_TOTAL"].forEach((k) => {
      if (obj[k] !== undefined && obj[k] !== "") obj[k] = Number(obj[k]);
    });
    return obj;
  }

  function showRateLimitHeaders(res) {
    const limit = res.headers.get("X-RateLimit-Limit");
    const remain = res.headers.get("X-RateLimit-Remaining");
    const reset = res.headers.get("X-RateLimit-Reset");
    console.log("limit, remain, reset")
    console.log(limit, remain, reset)
    if (limit || remain || reset) {
      rateMeta.style.display = "flex";
      rlLimit.textContent = `Limit: ${limit ?? "-"}`;
      rlRemain.textContent = `Remaining: ${remain ?? "-"}`;
      rlReset.textContent = reset
        ? `Reset@ ${new Date(Number(reset) * 1000).toLocaleString()}`
        : "Reset: -";
    } else {
      rateMeta.style.display = "none";
    }
  }

  function enableDownloads(enabled) {
    btnDlSvg.disabled = !enabled;
    btnDlJson.disabled = !enabled;
  }

  async function runSimulate(payload) {
    console.log("===== runSimulate STARTED ======")
    console.log(payload)
    console.log(window.location.href)
    const res = await fetch("/api/simulate", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "accept": "application/json"
      },
      body: JSON.stringify(payload),
    });
    console.log("res : ")
    console.log(res)

    showRateLimitHeaders(res);

    // Content-Type이 JSON이 아니면 HTML/텍스트를 그대로 미리보기로 에러 표시
    const ctype = (res.headers.get("content-type") || "").toLowerCase();
    if (!ctype.includes("application/json")) {
      const preview = await res.text().catch(() => "");
      const head = preview.slice(0, 300).replace(/\s+/g, " ").trim();
      throw new Error(
        `Non-JSON response (status ${res.status})\n` +
        `Content-Type: ${ctype || "-"}\n` +
        `Preview: ${head || "<empty>"}` +
        `\n(라우팅/핸들러 확인: /api/simulate가 정적 에셋으로 가지 않도록)`
      );
    }

    // JSON 파싱
    let data;
    try {
      data = await res.json();
    } catch (e) {
      throw new Error(`JSON parse error (status ${res.status}): ${String(e)}`);
    }

    if (!res.ok || !data?.ok) {
      const msg = (data && (data.error || data.message)) || `HTTP ${res.status}`;
      throw new Error(msg);
    }

    return data;
  }

  function setPlotFromSvg(svgText) {
    const url = URL.createObjectURL(
      new Blob([svgText], { type: "image/svg+xml;charset=utf-8" })
    );
    plotEl.src = url;
    plotEl.classList.add("show");
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    enableDownloads(false);
    plotEl.classList.remove("show");
    plotEl.removeAttribute("src");
    lastSvgText = null;
    lastSummary = null;

    const payload = readForm(form);
    summaryEl.textContent = "running…";

    try {
      const data = await runSimulate(payload);

      lastSummary = data.summary || null;

      // 한국어로 렌더링
      if (lastSummary) {
        renderSummary(lastSummary);
      } else {
        summaryEl.textContent = "데이터 없음";
      }

      if (data.image_svg) {
        lastSvgText = data.image_svg;
        setPlotFromSvg(lastSvgText);
        enableDownloads(true);
      } else {
        enableDownloads(false);
      }
    } catch (err) {
      console.error(err);
      summaryEl.textContent = `오류: ${String(err.message || err)}`;
      enableDownloads(false);
    }
  });

  btnReset.addEventListener("click", () => {
    summaryEl.textContent = "ready";
    plotEl.classList.remove("show");
    plotEl.removeAttribute("src");
    lastSvgText = null;
    lastSummary = null;
    enableDownloads(false);
  });

  btnDlSvg.addEventListener("click", () => {
    if (!lastSvgText) return;
    const blob = new Blob([lastSvgText], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    a.download = `distribution-${ts}.svg`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  });

  btnDlJson.addEventListener("click", () => {
    if (!lastSummary) return;
    const blob = new Blob(
      [JSON.stringify(lastSummary, null, 2)],
      { type: "application/json;charset=utf-8" }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    a.href = url;
    a.download = `summary-${ts}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  });
})();
