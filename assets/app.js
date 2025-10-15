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

  let lastSvgText = null;
  let lastSummary = null;

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

  function getPercentileColor(percentile) {
    if (percentile >= 95) return "#FFD700"; // 금색
    if (percentile >= 90) return "#4169E1"; // 파란색
    if (percentile >= 50) return "#32CD32"; // 초록색
    if (percentile >= 10) return "#FF8C00"; // 주황색
    return "#DC143C"; // 빨강색
  }

  function formatSummary(summary) {
    if (!summary) return "ready";

    // percentile_rank_of_obs_% 값 추출
    const percentileKey = "percentile_rank_of_obs_%";
    const percentile = summary[percentileKey];

    // percentile을 제외한 나머지 항목들
    const otherKeys = Object.keys(summary).filter(k => k !== percentileKey);

    // HTML 생성
    let html = '<div style="font-family: ui-monospace, monospace; line-height: 1.8;">';

    // 1. 관측 상위비율을 가장 위에 표시 (색상 하이라이트)
    if (percentile !== undefined) {
      const color = getPercentileColor(percentile);
      html += `<div style="margin-bottom: 12px; padding: 8px; background: rgba(0,0,0,0.2); border-radius: 8px;">`;
      html += `<span style="color: #94a3b8;">${percentileKey}:</span> `;
      html += `<span style="color: ${color}; font-weight: bold; font-size: 1.1em;">${percentile.toFixed(2)}</span>`;
      html += `</div>`;
    }

    // 2. 나머지 항목들 표시
    otherKeys.forEach(key => {
      const value = summary[key];
      const displayValue = typeof value === 'number' ? value.toFixed(4) : value;
      html += `<div style="margin-bottom: 4px;">`;
      html += `<span style="color: #94a3b8;">${key}:</span> `;
      html += `<span style="color: #e5e7eb;">${displayValue}</span>`;
      html += `</div>`;
    });

    html += '</div>';
    return html;
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
      summaryEl.innerHTML = formatSummary(lastSummary);

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
