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
    // 숫자 변환
    ["GAME_ID","GOAL","OBS_TOTAL","N_SIMS","BINS","SEED"].forEach((k) => {
      if (obj[k] !== undefined && obj[k] !== "") {
        obj[k] = Number(obj[k]);
      }
    });
    return obj;
  }

  function showRateLimitHeaders(res) {
    const limit = res.headers.get("X-RateLimit-Limit");
    const remain = res.headers.get("X-RateLimit-Remaining");
    const reset = res.headers.get("X-RateLimit-Reset");

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
    const res = await fetch("/api/simulate", {
      method: "POST",
      headers: { "content-type": "application/json", "accept": "application/json" },
      body: JSON.stringify(payload),
    });
    showRateLimitHeaders(res);
    const data = await res.json();
    if (!res.ok || !data.ok) {
      const msg = data?.error || `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return data;
  }

  function setPlotFromSvg(svgText) {
    // Blob URL로 표시
    const url = URL.createObjectURL(new Blob([svgText], { type: "image/svg+xml;charset=utf-8" }));
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
      // 요약 출력
      lastSummary = data.summary || null;
      summaryEl.textContent = JSON.stringify(data.summary, null, 2);

      // SVG 표시
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

  // 다운로드: SVG
  btnDlSvg.addEventListener("click", () => {
    if (!lastSvgText) return;
    const blob = new Blob([lastSvgText], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const now = new Date();
    const ts = now.toISOString().replace(/[:.]/g, "-");
    a.download = `distribution-${ts}.svg`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  });

  // 다운로드: JSON (summary)
  btnDlJson.addEventListener("click", () => {
    if (!lastSummary) return;
    const blob = new Blob([JSON.stringify(lastSummary, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const now = new Date();
    const ts = now.toISOString().replace(/[:.]/g, "-");
    a.href = url;
    a.download = `summary-${ts}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  });
})();
