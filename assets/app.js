/* global Toastify */
function toast(msg, type = "info") {
  // 색상 프리셋
  const bg = {
    info: "linear-gradient(135deg, #4a90e2, #9013fe)",
    success: "linear-gradient(135deg, #00c853, #00acc1)",
    error: "linear-gradient(135deg, #ff416c, #ff4b2b)",
    warn: "linear-gradient(135deg, #ffb300, #fb8c00)",
  }[type] || "linear-gradient(135deg, #4a90e2, #9013fe)";

  Toastify({ text: msg, duration: 2500, gravity: "top", position: "right", backgroundColor: bg }).showToast();
}

async function runSimulate(payload) {
  const res = await fetch("/api/simulate", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

function getFormValues() {
  const game = Number(document.getElementById("game").value);
  const goal = Number(document.getElementById("goal").value);
  const obs  = Number(document.getElementById("obs").value);
  const sims = Number(document.getElementById("sims").value || 500000);
  const bins = Number(document.getElementById("bins").value || 128);
  const seed = Number(document.getElementById("seed").value || 20251014);

  return { GAME_ID: game, GOAL: goal, OBS_TOTAL: obs, N_SIMS: sims, BINS: bins, SEED: seed };
}

function setLoading(disabled) {
  document.getElementById("run").disabled = disabled;
  document.getElementById("reset").disabled = disabled;
}

document.getElementById("sim-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = getFormValues();

  // 간단 검증
  if (payload.GAME_ID < 1 || payload.GOAL < 1 || payload.OBS_TOTAL < 1) {
    toast("입력을 다시 확인해주세요.", "warn");
    return;
  }

  setLoading(true);
  toast("시뮬레이션 실행 중…", "info");
  const summaryEl = document.getElementById("summary");
  const plotEl = document.getElementById("plot");
  summaryEl.textContent = "Running…";

  try {
    const data = await runSimulate(payload);
    if (!data.ok) throw new Error(data.error || "unknown error");

    // Summary JSON 표시
    summaryEl.textContent = JSON.stringify(data.summary, null, 2);

    // 이미지 표시
    plotEl.src = data.image_data_url || "";
    if (plotEl.src) {
      plotEl.classList.add("show");
    }

    toast("완료되었습니다.", "success");
  } catch (err) {
    console.error(err);
    toast(`실패: ${err.message}`, "error");
    summaryEl.textContent = `Error: ${err.message}`;
  } finally {
    setLoading(false);
  }
});

document.getElementById("reset").addEventListener("click", () => {
  document.getElementById("game").value = 1;
  document.getElementById("goal").value = 7;
  document.getElementById("obs").value = 888;
  document.getElementById("sims").value = 500000;
  document.getElementById("bins").value = 128;
  document.getElementById("seed").value = 20251014;
  document.getElementById("summary").textContent = '{"status":"ready"}';
  document.getElementById("plot").src = "";
  toast("초기화했습니다.", "info");
});
