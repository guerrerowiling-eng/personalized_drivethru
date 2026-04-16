/**
 * Café Barista — Operador: polling, sugerencias, menú y registro de visitas.
 */

const POLL_INTERVAL_MS = 2000;
const PREVIEW_INTERVAL_MS = 180;

let lastServerPlate = null;
let cameraPreviewTimer = null;
let differentOrderMode = false;
let pendingOrder = null;
let menuCategories = [];
let filterText = "";
/** @type {object | null} */
let lastState = null;
let appliedCameraMode = null;

const elements = {
    displayCard: document.getElementById("displayCard"),
    greeting: document.getElementById("greeting"),
    customerName: document.getElementById("customerName"),
    plateBadge: document.getElementById("plateBadge"),
    orderHint: document.getElementById("orderHint"),
    visitsBadge: document.getElementById("visitsBadge"),
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
    btnOpenMenu: document.getElementById("btnOpenMenu"),
    pendingBar: document.getElementById("pendingBar"),
    pendingLabel: document.getElementById("pendingLabel"),
    btnConfirmVisit: document.getElementById("btnConfirmVisit"),
    errorToast: document.getElementById("errorToast"),
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
    clearTimeout(showError._t);
    showError._t = setTimeout(() => {
        elements.errorToast.hidden = true;
    }, 4500);
}

function resetSessionForPlate(plate) {
    if (plate !== lastServerPlate) {
        differentOrderMode = false;
        pendingOrder = null;
        elements.customerNameInput.value = "";
        elements.pendingBar.hidden = true;
        lastServerPlate = plate;
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
            b.addEventListener("click", () => onPickMenuItem(item));
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
    elements.menuBackdrop.hidden = false;
    elements.menuSheet.hidden = false;
    setMenuAriaOpen(true);
    elements.menuFilter.value = filterText;
    renderMenu();
    elements.menuFilter.focus();
}

/**
 * Cierra el panel del menú. No borra pendingOrder ni el pedido en curso.
 */
function closeMenu() {
    elements.menuBackdrop.hidden = true;
    elements.menuSheet.hidden = true;
    setMenuAriaOpen(false);
    filterText = "";
    elements.menuFilter.value = "";
}

function onPickMenuItem(item) {
    pendingOrder = item;
    closeMenu();
    elements.pendingLabel.textContent = `Pedido: ${item}`;
    elements.pendingBar.hidden = false;
}

function updateNameRow(state) {
    const isNew = state.type === "new";
    elements.nameRow.hidden = !isNew;
    if (isNew && state.hint_nombre && !elements.customerNameInput.value.trim()) {
        elements.customerNameInput.value = state.hint_nombre;
    }
}

function updateDisplay(state) {
    lastState = state;
    elements.displayCard.classList.remove("returning", "new-customer");

    if (state.type === "idle") {
        elements.greeting.textContent = state.message;
        elements.customerName.textContent = "";
        elements.plateBadge.textContent = "";
        elements.orderHint.textContent = "";
        elements.visitsBadge.textContent = "";
        elements.actionPanel.hidden = true;
        lastServerPlate = null;
        differentOrderMode = false;
        pendingOrder = null;
        elements.pendingBar.hidden = true;
        elements.customerNameInput.value = "";
    } else {
        resetSessionForPlate(state.plate);
        elements.plateBadge.textContent = state.plate || "";

        if (state.type === "returning") {
            elements.displayCard.classList.add("returning");
            elements.greeting.textContent = state.message || "";
            elements.customerName.textContent = state.customer
                ? state.customer.nombre
                : "";
        } else {
            elements.displayCard.classList.add("new-customer");
            elements.greeting.textContent = state.message || "";
            elements.customerName.textContent = "";
        }

        const pv = state.prior_visits ?? 0;
        elements.visitsBadge.textContent =
            pv > 0 ? `Visitas registradas: ${pv}` : "Primera visita en historial";

        const showSug =
            state.show_suggestion_actions &&
            state.suggested_order &&
            !differentOrderMode;

        elements.actionPanel.hidden = false;
        elements.suggestionActions.hidden = !showSug;

        if (differentOrderMode) {
            elements.orderHint.textContent = "Elige otro pedido en el menú";
        } else if (state.suggestion_text) {
            elements.orderHint.textContent = state.suggestion_text;
        } else if (state.type === "returning" && state.prior_visits === 0) {
            elements.orderHint.textContent = "Sin sugerencia — primera visita en historial";
        } else {
            elements.orderHint.textContent = "";
        }

        updateNameRow(state);
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
        updateDisplay(state);
    } catch (err) {
        console.warn("Polling:", err);
    }
}

function activePlate() {
    if (lastState && lastState.plate) return lastState.plate;
    return elements.plateInput.value.trim();
}

async function recordVisit(orden, nombreOverride) {
    const plate = activePlate();
    if (!plate) {
        showError("No hay placa activa.");
        return;
    }
    const body = { plate, orden };
    const name = (nombreOverride ?? elements.customerNameInput.value).trim();
    if (name) body.nombre = name;

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
        pendingOrder = null;
        differentOrderMode = false;
        elements.pendingBar.hidden = true;
        if (data.state) updateDisplay(data.state);
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
    if (!lastState || !lastState.suggested_order) return;
    if (lastState.type === "new") {
        const nombre = elements.customerNameInput.value.trim();
        if (!nombre) {
            showError("Escribe el nombre del cliente");
            elements.customerNameInput.focus();
            return;
        }
        recordVisit(lastState.suggested_order, nombre);
    } else {
        recordVisit(lastState.suggested_order);
    }
});

elements.btnDifferentOrder.addEventListener("click", () => {
    differentOrderMode = true;
    elements.suggestionActions.hidden = true;
    elements.orderHint.textContent = "Elige otro pedido en el menú";
    openMenu();
});

elements.btnOpenMenu.addEventListener("click", () => {
    openMenu();
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
    if (elements.menuSheet.hidden) return;
    closeMenu();
});

elements.menuFilter.addEventListener("input", () => {
    filterText = elements.menuFilter.value;
    renderMenu();
});

elements.btnConfirmVisit.addEventListener("click", () => {
    if (!pendingOrder) {
        showError("Elige un ítem del menú");
        return;
    }
    if (lastState && lastState.type === "new") {
        const nombre = elements.customerNameInput.value.trim();
        if (!nombre) {
            showError("Escribe el nombre del cliente");
            elements.customerNameInput.focus();
            return;
        }
        recordVisit(pendingOrder, nombre);
    } else {
        recordVisit(pendingOrder);
    }
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

fetchMenuOnce();
fetchCurrentState();
setInterval(fetchCurrentState, POLL_INTERVAL_MS);
