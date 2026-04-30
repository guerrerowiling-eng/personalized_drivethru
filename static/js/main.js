/**
 * Café Barista — Operador: polling, sugerencias, carrito y registro de visitas.
 */

const POLL_INTERVAL_MS = 2000;
const PREVIEW_INTERVAL_MS = 180;
const MAX_CART_UNITS = 10;

let lastServerPlate = null;
let cameraPreviewTimer = null;
let differentOrderMode = false;
let menuCategories = [];
let filterText = "";
/** @type {object | null} */
let lastState = null;
let appliedCameraMode = null;
let nicknameModalOpen = false;

/** Carrito: modo armado de pedido */
let cartBuilding = false;
let cartPlate = null;
/** @type {'otro' | 'new_customer' | 'menu'} */
let cartOrderSource = "menu";
/** @type {{ item: string, quantity: number }[]} */
let cartLines = [];
let cartMenuFilterText = "";

const elements = {
    displayCard: document.getElementById("displayCard"),
    greeting: document.getElementById("greeting"),
    plateBadge: document.getElementById("plateBadge"),
    orderHint: document.getElementById("orderHint"),
    plateInput: document.getElementById("plateInput"),
    btnLookup: document.getElementById("btnLookup"),
    btnSimulate: document.getElementById("btnSimulate"),
    lastPlate: document.getElementById("lastPlate"),
    actionPanel: document.getElementById("actionPanel"),
    suggestionActions: document.getElementById("suggestionActions"),
    btnSameOrder: document.getElementById("btnSameOrder"),
    btnDifferentOrder: document.getElementById("btnDifferentOrder"),
    nameRow: document.getElementById("nameRow"),
    customerNameInput: document.getElementById("customerNameInput"),
    btnSaveNickname: document.getElementById("btnSaveNickname"),
    btnOpenMenu: document.getElementById("btnOpenMenu"),
    pendingBar: document.getElementById("pendingBar"),
    pendingLabel: document.getElementById("pendingLabel"),
    btnConfirmVisit: document.getElementById("btnConfirmVisit"),
    errorToast: document.getElementById("errorToast"),
    successToast: document.getElementById("successToast"),
    menuBackdrop: document.getElementById("menuBackdrop"),
    menuSheet: document.getElementById("menuSheet"),
    menuBody: document.getElementById("menuBody"),
    menuFilter: document.getElementById("menuFilter"),
    btnCloseMenu: document.getElementById("btnCloseMenu"),
    btnCloseMenuFooter: document.getElementById("btnCloseMenuFooter"),
    cameraPreviewImg: document.getElementById("cameraPreviewImg"),
    cameraPreviewPlaceholder: document.getElementById("cameraPreviewPlaceholder"),
    cameraModeLabel: document.getElementById("cameraModeLabel"),
    btnCameraToggle: document.getElementById("btnCameraToggle"),
    btnEditNickname: document.getElementById("btnEditNickname"),
    nicknameModalBackdrop: document.getElementById("nicknameModalBackdrop"),
    nicknameModal: document.getElementById("nicknameModal"),
    nicknameModalInput: document.getElementById("nicknameModalInput"),
    btnCancelNicknameModal: document.getElementById("btnCancelNicknameModal"),
    btnSaveNicknameModal: document.getElementById("btnSaveNicknameModal"),
    cartBuildingShell: document.getElementById("cartBuildingShell"),
    cartMenuBody: document.getElementById("cartMenuBody"),
    cartMenuFilter: document.getElementById("cartMenuFilter"),
    cartHeaderCount: document.getElementById("cartHeaderCount"),
    cartRows: document.getElementById("cartRows"),
    cartEmptyState: document.getElementById("cartEmptyState"),
    btnConfirmCart: document.getElementById("btnConfirmCart"),
    linkCancelCart: document.getElementById("linkCancelCart"),
};

function stopCameraPreview() {
    if (cameraPreviewTimer) {
        clearInterval(cameraPreviewTimer);
        cameraPreviewTimer = null;
    }
}

function fetchOneCameraPreview() {
    elements.cameraPreviewImg.src = `/api/camera-preview?t=${Date.now()}`;
}

function startCameraPreview() {
    stopCameraPreview();
    elements.cameraPreviewImg.hidden = false;
    elements.cameraPreviewPlaceholder.hidden = false;
    elements.cameraPreviewPlaceholder.textContent = "Cargando cámara…";
    fetchOneCameraPreview();
    cameraPreviewTimer = setInterval(fetchOneCameraPreview, PREVIEW_INTERVAL_MS);
}

function syncCameraUi(mode) {
    const m = mode === "real" ? "real" : "simulated";
    if (m === appliedCameraMode) return;
    appliedCameraMode = m;

    if (m === "real") {
        elements.cameraModeLabel.textContent = "Modo: cámara real";
        elements.btnCameraToggle.textContent = "Usar simulación";
        elements.btnSimulate.textContent = "Detectar placa";
        startCameraPreview();
    } else {
        stopCameraPreview();
        elements.cameraModeLabel.textContent = "Modo: simulado";
        elements.btnCameraToggle.textContent = "Usar cámara real";
        elements.btnSimulate.textContent = "Simular llegada";
        elements.cameraPreviewImg.hidden = true;
        elements.cameraPreviewImg.removeAttribute("src");
        elements.cameraPreviewPlaceholder.hidden = false;
        elements.cameraPreviewPlaceholder.textContent =
            "Vista previa solo en modo cámara real";
    }
}

function showError(msg) {
    elements.errorToast.textContent = msg;
    elements.errorToast.hidden = false;
    elements.successToast.hidden = true;
    clearTimeout(showError._t);
    showError._t = setTimeout(() => {
        elements.errorToast.hidden = true;
    }, 4500);
}

function showSuccess(msg) {
    elements.successToast.textContent = msg;
    elements.successToast.hidden = false;
    elements.errorToast.hidden = true;
    clearTimeout(showSuccess._t);
    showSuccess._t = setTimeout(() => {
        elements.successToast.hidden = true;
    }, 3200);
}

function cartTotalUnits() {
    return cartLines.reduce((s, r) => s + r.quantity, 0);
}

function exitCartBuildingNoRefetch() {
    cartBuilding = false;
    cartPlate = null;
    cartLines = [];
    cartMenuFilterText = "";
    if (elements.cartBuildingShell) elements.cartBuildingShell.hidden = true;
    if (elements.cartMenuFilter) elements.cartMenuFilter.value = "";
}

function enterCartBuilding(source) {
    cartOrderSource = source;
    cartBuilding = true;
    cartPlate = activePlate();
    cartLines = [];
    cartMenuFilterText = "";
    if (elements.cartMenuFilter) elements.cartMenuFilter.value = "";
    document.body.dataset.viewState = "cart_building";
    if (elements.cartBuildingShell) elements.cartBuildingShell.hidden = false;
    elements.actionPanel.hidden = true;
    elements.orderHint.textContent = "Arma el pedido abajo";
    renderCartMenu();
    renderCartRows();
    elements.pendingBar.hidden = true;
}

function renderCartMenu() {
    if (!elements.cartMenuBody) return;
    const q = cartMenuFilterText.trim().toLowerCase();
    const atMax = cartTotalUnits() >= MAX_CART_UNITS;
    elements.cartMenuBody.innerHTML = "";
    for (const cat of menuCategories) {
        const items = cat.items.filter((it) => !q || it.toLowerCase().includes(q));
        if (!items.length) continue;
        const section = document.createElement("section");
        section.className = "menu-category";
        const h = document.createElement("h3");
        h.textContent = cat.titulo;
        section.appendChild(h);
        const grid = document.createElement("div");
        grid.className = "menu-items";
        for (const item of items) {
            const b = document.createElement("button");
            b.type = "button";
            b.className = "menu-item-btn cart-menu-item-btn";
            b.textContent = item;
            if (atMax) {
                b.classList.add("menu-item-btn--disabled");
                b.disabled = true;
            }
            b.addEventListener("click", () => {
                if (cartTotalUnits() >= MAX_CART_UNITS) return;
                addToCartLine(item);
            });
            grid.appendChild(b);
        }
        section.appendChild(grid);
        elements.cartMenuBody.appendChild(section);
    }
    if (!elements.cartMenuBody.children.length) {
        const p = document.createElement("p");
        p.className = "menu-empty";
        p.textContent = "Sin resultados.";
        elements.cartMenuBody.appendChild(p);
    }
}

function addToCartLine(itemName) {
    if (cartTotalUnits() >= MAX_CART_UNITS) return;
    const existing = cartLines.find((r) => r.item === itemName);
    if (existing) {
        if (cartTotalUnits() >= MAX_CART_UNITS) return;
        existing.quantity += 1;
    } else {
        cartLines.push({ item: itemName, quantity: 1 });
    }
    renderCartRows();
    renderCartMenu();
}

function renderCartRows() {
    const total = cartTotalUnits();
    if (elements.cartHeaderCount) {
        elements.cartHeaderCount.textContent = `Pedido (${total} de 10 items)`;
    }
    const empty = total === 0;
    if (elements.cartEmptyState) {
        elements.cartEmptyState.hidden = !empty;
    }
    if (elements.btnConfirmCart) {
        elements.btnConfirmCart.disabled = empty;
    }
    if (!elements.cartRows) return;
    elements.cartRows.innerHTML = "";
    for (let i = 0; i < cartLines.length; i++) {
        const row = cartLines[i];
        const wrap = document.createElement("div");
        wrap.className = "cart-row";
        const name = document.createElement("span");
        name.className = "cart-row-name";
        name.textContent = row.item;

        const minus = document.createElement("button");
        minus.type = "button";
        minus.className = "cart-qty-btn";
        minus.textContent = "−";
        minus.disabled = row.quantity <= 1;
        minus.addEventListener("click", () => {
            if (row.quantity > 1) {
                row.quantity -= 1;
                renderCartRows();
                renderCartMenu();
            }
        });

        const qty = document.createElement("span");
        qty.className = "cart-qty-val";
        qty.textContent = String(row.quantity);

        const plus = document.createElement("button");
        plus.type = "button";
        plus.className = "cart-qty-btn";
        plus.textContent = "+";
        plus.disabled = cartTotalUnits() >= MAX_CART_UNITS;
        plus.addEventListener("click", () => {
            if (cartTotalUnits() >= MAX_CART_UNITS) return;
            row.quantity += 1;
            renderCartRows();
            renderCartMenu();
        });

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "cart-remove-btn";
        remove.setAttribute("aria-label", "Quitar");
        remove.textContent = "✕";
        remove.addEventListener("click", () => {
            cartLines.splice(i, 1);
            renderCartRows();
            renderCartMenu();
        });

        wrap.appendChild(name);
        wrap.appendChild(minus);
        wrap.appendChild(qty);
        wrap.appendChild(plus);
        wrap.appendChild(remove);
        elements.cartRows.appendChild(wrap);
    }
}

function resetSessionForPlate(plate) {
    if (plate !== lastServerPlate) {
        differentOrderMode = false;
        elements.pendingBar.hidden = true;
        lastServerPlate = plate;
        if (!cartBuilding) {
            elements.customerNameInput.value = "";
        }
    }
}

function renderMenu() {
    const q = filterText.trim().toLowerCase();
    elements.menuBody.innerHTML = "";
    for (const cat of menuCategories) {
        const items = cat.items.filter((it) => !q || it.toLowerCase().includes(q));
        if (!items.length) continue;
        const section = document.createElement("section");
        section.className = "menu-category";
        const h = document.createElement("h3");
        h.textContent = cat.titulo;
        section.appendChild(h);
        const grid = document.createElement("div");
        grid.className = "menu-items";
        for (const item of items) {
            const b = document.createElement("button");
            b.type = "button";
            b.className = "menu-item-btn";
            b.textContent = item;
            b.addEventListener("click", () => {
                /* Menú legacy: redirige al carrito */
                enterCartBuilding("menu");
            });
            grid.appendChild(b);
        }
        section.appendChild(grid);
        elements.menuBody.appendChild(section);
    }
    if (!elements.menuBody.children.length) {
        const p = document.createElement("p");
        p.className = "menu-empty";
        p.textContent = "Sin resultados.";
        elements.menuBody.appendChild(p);
    }
}

function setMenuAriaOpen(open) {
    elements.menuBackdrop.setAttribute("aria-hidden", open ? "false" : "true");
    elements.menuSheet.setAttribute("aria-hidden", open ? "false" : "true");
}

function openMenu() {
    enterCartBuilding("menu");
}

function closeMenu() {
    elements.menuBackdrop.hidden = true;
    elements.menuSheet.hidden = true;
    setMenuAriaOpen(false);
    filterText = "";
    elements.menuFilter.value = "";
}

function updateNameRow(state) {
    const show = !!state.needs_nickname;
    elements.nameRow.hidden = !show;
    if (show && state.hint_nickname && !elements.customerNameInput.value.trim()) {
        elements.customerNameInput.value = state.hint_nickname;
    }
}

function setNicknameModalOpen(open) {
    nicknameModalOpen = !!open;
    elements.nicknameModalBackdrop.hidden = !open;
    elements.nicknameModal.hidden = !open;
    elements.nicknameModalBackdrop.setAttribute("aria-hidden", open ? "false" : "true");
    elements.nicknameModal.setAttribute("aria-hidden", open ? "false" : "true");
    if (open) {
        elements.nicknameModalInput.value = (lastState?.customer?.nickname || "").trim();
        elements.nicknameModalInput.focus();
    }
}

async function saveNicknameForCurrentPlate(nickname) {
    const plate = activePlate();
    if (!plate) {
        showError("No hay placa activa.");
        return false;
    }
    const nick = (nickname || "").trim();
    if (!nick) {
        showError("Escribe el apodo");
        return false;
    }
    try {
        const res = await fetch("/api/update-nickname", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ plate, nickname: nick }),
        });
        const data = await res.json();
        if (!data.ok) {
            showError(data.error || "No se pudo guardar el apodo");
            return false;
        }
        if (data.state) updateDisplay(data.state);
        return true;
    } catch (e) {
        console.error(e);
        showError("Error de red al guardar el apodo");
        return false;
    }
}

function suggestedOrderIsNonEmpty(order) {
    return Array.isArray(order) && order.length > 0;
}

function updateDisplay(state) {
    if (state.type === "idle" && cartBuilding) {
        exitCartBuildingNoRefetch();
    }
    lastState = state;
    elements.displayCard.classList.remove("returning", "new-customer", "detection-failed");
    if (!cartBuilding) {
        document.body.dataset.viewState = state.type || "idle";
    }

    if (state.type === "idle") {
        elements.greeting.textContent = state.message;
        elements.plateBadge.textContent = "";
        elements.orderHint.textContent = "";
        elements.actionPanel.hidden = true;
        elements.btnEditNickname.hidden = true;
        elements.btnOpenMenu.hidden = false;
        lastServerPlate = null;
        differentOrderMode = false;
        elements.pendingBar.hidden = true;
        elements.customerNameInput.value = "";
        if (elements.cartBuildingShell) elements.cartBuildingShell.hidden = true;
        cartBuilding = false;
        cartPlate = null;
        cartLines = [];
    } else if (state.type === "detection_failed") {
        elements.displayCard.classList.add("detection-failed");
        elements.greeting.textContent = state.message || "";
        elements.plateBadge.textContent = "";
        elements.orderHint.textContent = "";
        elements.actionPanel.hidden = true;
        elements.btnEditNickname.hidden = true;
        elements.btnOpenMenu.hidden = false;
        elements.nameRow.hidden = true;
        elements.pendingBar.hidden = true;
        lastServerPlate = null;
        differentOrderMode = false;
        exitCartBuildingNoRefetch();
    } else {
        resetSessionForPlate(state.plate);
        elements.plateBadge.textContent = state.plate ? `Placa ${state.plate}` : "";

        if (state.customer?.nickname) {
            elements.greeting.textContent = `¡Hola ${state.customer.nickname}!`;
        } else if (state.needs_nickname) {
            elements.greeting.textContent = "¡Bienvenido!";
        } else {
            elements.greeting.textContent = state.message || "¡Hola!";
        }

        if (state.type === "returning") {
            elements.displayCard.classList.add("returning");
        } else {
            elements.displayCard.classList.add("new-customer");
        }

        const sug = suggestedOrderIsNonEmpty(state.suggested_order);
        const showSug =
            state.show_suggestion_actions &&
            sug &&
            !differentOrderMode &&
            !state.needs_nickname &&
            !!state.customer?.nickname;

        if (!cartBuilding) {
            elements.actionPanel.hidden = false;
        }
        elements.suggestionActions.hidden = !showSug;
        elements.btnEditNickname.hidden = !state.customer?.nickname;
        elements.btnOpenMenu.hidden = !!state.needs_nickname;
        if (state.needs_nickname) {
            differentOrderMode = false;
            elements.suggestionActions.hidden = true;
        }

        if (cartBuilding) {
            /* No pisar el panel del carrito */
        } else if (differentOrderMode) {
            elements.orderHint.textContent = "Arma el pedido en el panel inferior";
        } else if (state.suggestion_text) {
            elements.orderHint.textContent = state.suggestion_text;
        } else if (state.type === "returning" && state.prior_visits === 0) {
            elements.orderHint.textContent = "Sin sugerencia — primera visita en historial";
        } else {
            elements.orderHint.textContent = "";
        }

        updateNameRow(state);
        if (state.needs_nickname) {
            elements.pendingBar.hidden = true;
        }
    }

    elements.lastPlate.textContent = state.plate ? `Placa: ${state.plate}` : "";

    if (state.camera_mode !== undefined) {
        syncCameraUi(state.camera_mode);
    }
}

async function fetchMenuOnce() {
    try {
        const res = await fetch("/api/menu");
        const data = await res.json();
        menuCategories = data.categories || [];
    } catch (e) {
        console.warn("Menú:", e);
    }
}

async function fetchCurrentState() {
    try {
        const res = await fetch("/api/current");
        const state = await res.json();
        if (cartBuilding && cartPlate) {
            if (!state.plate || state.plate !== cartPlate) {
                exitCartBuildingNoRefetch();
                updateDisplay(state);
                return;
            }
            if (state.camera_mode !== undefined) {
                syncCameraUi(state.camera_mode);
            }
            return;
        }
        updateDisplay(state);
    } catch (err) {
        console.warn("Polling:", err);
    }
}

function activePlate() {
    if (lastState && lastState.plate) return lastState.plate;
    return elements.plateInput.value.trim();
}

function suggestionAcceptedForCartConfirm() {
    if (cartOrderSource === "otro") return false;
    if (cartOrderSource === "new_customer" || cartOrderSource === "menu") return null;
    return null;
}

async function recordVisitWithItems(items, suggestionAccepted) {
    const plate = activePlate();
    if (!plate) {
        showError("No hay placa activa.");
        return;
    }
    const body = {
        plate,
        items,
        suggestion_accepted: suggestionAccepted,
    };
    const nick = (lastState?.customer?.nickname || elements.customerNameInput.value).trim();
    if (lastState?.type === "new" && !lastState?.customer?.nickname && !nick) {
        showError("Escribe cómo le gusta que le llamen");
        elements.customerNameInput.focus();
        return;
    }
    if (nick) body.nickname = nick;

    try {
        const res = await fetch("/api/record-visit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!data.ok) {
            showError(data.error || "No se pudo guardar");
            return;
        }
        showSuccess("Pedido guardado");
        differentOrderMode = false;
        exitCartBuildingNoRefetch();
        await setPlateOnServer("");
    } catch (e) {
        console.error(e);
        showError("Error de red al guardar");
    }
}

async function setPlateOnServer(plate) {
    try {
        const res = await fetch("/api/set-plate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ plate: plate.trim() || "" }),
        });
        const state = await res.json();
        updateDisplay(state);
    } catch (err) {
        console.error(err);
    }
}

async function simulateArrival() {
    try {
        const res = await fetch("/api/simulate-arrival");
        const state = await res.json();
        updateDisplay(state);
    } catch (err) {
        console.error(err);
    }
}

elements.btnSameOrder.addEventListener("click", () => {
    if (!lastState || !suggestedOrderIsNonEmpty(lastState.suggested_order)) return;
    if (lastState.type === "new") {
        const nickname = (lastState.customer?.nickname || elements.customerNameInput.value).trim();
        if (!nickname) {
            showError("Escribe cómo le gusta que le llamen");
            elements.customerNameInput.focus();
            return;
        }
    }
    const copy = JSON.parse(JSON.stringify(lastState.suggested_order));
    recordVisitWithItems(copy, true);
});

elements.btnDifferentOrder.addEventListener("click", () => {
    differentOrderMode = true;
    elements.suggestionActions.hidden = true;
    elements.orderHint.textContent = "Arma el pedido en el panel inferior";
    enterCartBuilding("otro");
});

elements.btnOpenMenu.addEventListener("click", () => {
    if (lastState?.needs_nickname) return;
    enterCartBuilding("menu");
});

elements.btnCloseMenu.addEventListener("click", (e) => {
    e.preventDefault();
    closeMenu();
});
elements.btnCloseMenuFooter.addEventListener("click", (e) => {
    e.preventDefault();
    closeMenu();
});
elements.menuBackdrop.addEventListener("click", closeMenu);
elements.menuSheet.addEventListener("click", (e) => {
    e.stopPropagation();
});

document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (nicknameModalOpen) {
        setNicknameModalOpen(false);
        return;
    }
    if (!elements.menuSheet.hidden) {
        closeMenu();
        return;
    }
    if (cartBuilding && elements.cartBuildingShell && !elements.cartBuildingShell.hidden) {
        elements.linkCancelCart.click();
    }
});

elements.menuFilter.addEventListener("input", () => {
    filterText = elements.menuFilter.value;
    renderMenu();
});

if (elements.cartMenuFilter) {
    elements.cartMenuFilter.addEventListener("input", () => {
        cartMenuFilterText = elements.cartMenuFilter.value;
        renderCartMenu();
    });
}

elements.btnConfirmCart.addEventListener("click", () => {
    if (!cartLines.length) return;
    const items = cartLines.map((r) => ({ item: r.item, quantity: r.quantity }));
    const sa = suggestionAcceptedForCartConfirm();
    recordVisitWithItems(items, sa);
});

elements.linkCancelCart.addEventListener("click", async () => {
    differentOrderMode = false;
    exitCartBuildingNoRefetch();
    await fetchCurrentState();
});

elements.btnSaveNickname.addEventListener("click", async () => {
    const ok = await saveNicknameForCurrentPlate(elements.customerNameInput.value);
    if (!ok) return;
    elements.customerNameInput.value = "";
    enterCartBuilding("new_customer");
});

elements.btnLookup.addEventListener("click", () => {
    const plate = elements.plateInput.value;
    if (plate.trim()) setPlateOnServer(plate);
});

elements.plateInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
        const plate = elements.plateInput.value;
        if (plate.trim()) setPlateOnServer(plate);
    }
});

elements.btnSimulate.addEventListener("click", simulateArrival);

elements.btnCameraToggle.addEventListener("click", async () => {
    const cur =
        lastState && lastState.camera_mode ? lastState.camera_mode : "simulated";
    const next = cur === "real" ? "simulated" : "real";
    try {
        const res = await fetch("/api/camera-mode", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode: next }),
        });
        const data = await res.json();
        if (!data.ok) {
            showError(data.error || "No se pudo cambiar el modo de cámara");
            return;
        }
        appliedCameraMode = null;
        syncCameraUi(data.effective);
        await fetchCurrentState();
    } catch (e) {
        console.error(e);
        showError("Error de red al cambiar modo de cámara");
    }
});

elements.cameraPreviewImg.addEventListener("load", () => {
    elements.cameraPreviewImg.hidden = false;
    elements.cameraPreviewPlaceholder.hidden = true;
});

elements.cameraPreviewImg.addEventListener("error", () => {
    elements.cameraPreviewImg.hidden = true;
    elements.cameraPreviewPlaceholder.hidden = false;
    elements.cameraPreviewPlaceholder.textContent = "Vista previa no disponible";
});

elements.btnEditNickname.addEventListener("click", () => {
    setNicknameModalOpen(true);
});

elements.btnCancelNicknameModal.addEventListener("click", () => {
    setNicknameModalOpen(false);
});

elements.nicknameModalBackdrop.addEventListener("click", () => {
    setNicknameModalOpen(false);
});

elements.btnSaveNicknameModal.addEventListener("click", async () => {
    const ok = await saveNicknameForCurrentPlate(elements.nicknameModalInput.value);
    if (!ok) return;
    setNicknameModalOpen(false);
});

/* Menú lateral legacy no usado en flujo principal (el carrito reemplaza la selección única) */
elements.pendingBar.hidden = true;

fetchMenuOnce();
fetchCurrentState();
setInterval(fetchCurrentState, POLL_INTERVAL_MS);
