const f = document.getElementById("f");
const statusEl = document.getElementById("status");

f.addEventListener("submit", async (e) => {
  e.preventDefault();
  statusEl.textContent = "processing...";
  const title = new FormData(f).get("title");

  // 임의 데이터
  const points = [[0,0],[10,20],[20,10],[30,30],[40,25]];
  const resp = await fetch("/api/process", {
    method: "POST",
    headers: {"content-type":"application/json"},
    body: JSON.stringify({ title, points })
  });

  // HTML 페이지로 응답 → 현재 탭에서 교체
  const html = await resp.text();
  document.open(); document.write(html); document.close();
});
