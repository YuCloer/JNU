/* Extra lineup-pool controls kept separate from the app's core UI. */
(() => {
  function profileAvatar(player, extraClass = "") {
    const avatar = document.createElement("div");
    avatar.className = `avatar ${extraClass}`.trim();
    const fallback = document.createElement("span");
    fallback.className = "avatar-placeholder";
    fallback.setAttribute("aria-hidden", "true");
    avatar.append(fallback);
    if (player.avatar_url) {
      const image = document.createElement("img");
      image.src = player.avatar_url;
      image.alt = "";
      image.loading = "lazy";
      image.referrerPolicy = "no-referrer";
      image.onload = () => avatar.classList.add("has-image");
      image.onerror = () => image.remove();
      avatar.prepend(image);
    }
    return avatar;
  }

  function addPoolControls() {
    const pool = document.querySelector(".pool");
    if (!pool || pool.dataset.enhanced === "true") return;
    const poolPlayers = editorPlayers();
    // The editor is re-rendered after every selection. Keep these UI-only
    // values on the active draft so a club search can be used repeatedly.
    const filterState = activeLineup.poolFilters || (activeLineup.poolFilters = { query: "", position: "" });
    pool.dataset.enhanced = "true";

    const heading = [...document.querySelectorAll(".panel h3")].find((item) => item.textContent.trim() === "球员池");
    if (heading) heading.innerHTML = `球员池 <span class="pill">${poolPlayers.length} 人</span>`;

    const filters = document.createElement("div");
    filters.className = "pool-filters";
    filters.innerHTML = `
      <input type="search" aria-label="搜索球员池" placeholder="搜索球员或俱乐部">
      <select aria-label="按位置筛选">
        <option value="">全部位置</option>
        <option value="GK">GK 门将</option><option value="LB">LB 左后卫</option>
        <option value="CB">CB 中卫</option><option value="RB">RB 右后卫</option>
        <option value="DM">DM 后腰</option><option value="CM">CM 中场</option>
        <option value="AM">AM 前腰</option><option value="LW">LW 左边锋</option>
        <option value="ST">ST 中锋</option><option value="RW">RW 右边锋</option>
      </select>`;
    pool.before(filters);
    const searchInput = filters.querySelector("input");
    const positionSelect = filters.querySelector("select");
    searchInput.value = filterState.query;
    positionSelect.value = filterState.position;

    const cards = [...pool.querySelectorAll(".pool-player")];
    cards.forEach((card, index) => {
      const player = poolPlayers[index];
      if (!player) return;
      card.prepend(profileAvatar(player, "pool-player-avatar"));
      card.dataset.search = `${player.name || ""} ${player.name_zh || ""} ${player.club_name || ""}`.toLowerCase();
      card.dataset.position = player.position || "";
      const detail = card.querySelector(".sub");
      if (detail) detail.textContent = `${player.club_name || ""} · ${player.age || "?"} 岁`;
    });

    const update = () => {
      filterState.query = searchInput.value;
      filterState.position = positionSelect.value;
      const keyword = filterState.query.trim().toLowerCase();
      const position = filterState.position;
      cards.forEach((card) => {
        const show = (!keyword || card.dataset.search.includes(keyword)) && (!position || card.dataset.position === position);
        card.hidden = !show;
      });
    };
    searchInput.addEventListener("input", update);
    positionSelect.addEventListener("change", update);
    update();
  }

  function addLineupAvatars() {
    if (!activeLineup) return;
    const orderedSlots = [
      ...activeLineup.slots.filter((slot) => slot.role === "STARTER"),
      ...activeLineup.slots.filter((slot) => slot.role === "SUBSTITUTE"),
    ];
    document.querySelectorAll(".slot").forEach((slotElement, index) => {
      if (slotElement.dataset.avatarEnhanced === "true") return;
      const slot = orderedSlots[index];
      const player = slot && players.find((item) => item.id === slot.player_id);
      const circle = slotElement.querySelector(".circle");
      if (!player || !circle) return;
      slotElement.dataset.avatarEnhanced = "true";
      circle.replaceWith(profileAvatar(player, "lineup-player-avatar"));
    });
  }

  const coreRender = window.renderEditor;
  window.renderEditor = function enhancedRenderEditor() {
    coreRender();
    addPoolControls();
    addLineupAvatars();
  };
})();
