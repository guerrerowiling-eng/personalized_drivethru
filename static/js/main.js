/**
 * Drive-Thru Operator Interface
 * Polling + updates cuando llega un cliente
 */

const POLL_INTERVAL_MS = 2000;
let lastDisplayedPlate = null;

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
};

function updateDisplay(state) {
    elements.displayCard.classList.remove("returning", "new-customer");

    if (state.type === "idle") {
        elements.greeting.textContent = state.message;
        elements.customerName.textContent = "";
        elements.plateBadge.textContent = "";
        elements.orderHint.textContent = "";
        elements.visitsBadge.textContent = "";
        lastDisplayedPlate = null;
    } else {
        elements.plateBadge.textContent = state.plate || "";

        if (state.type === "returning" && state.customer) {
            elements.displayCard.classList.add("returning");
            elements.greeting.textContent = state.message || `Hola ${state.customer.nombre}`;
            elements.customerName.textContent = "";
            elements.orderHint.textContent = "";
            elements.visitsBadge.textContent =
                state.customer.visitas > 0
                    ? `Cliente frecuente · ${state.customer.visitas} visitas`
                    : "";
        } else if (state.type === "new") {
            elements.displayCard.classList.add("new-customer");
            elements.greeting.textContent =
                state.message || "¡Bienvenido! Pregunta su nombre";
            elements.customerName.textContent = "";
            elements.orderHint.textContent = "";
            elements.visitsBadge.textContent = "";
        }

        lastDisplayedPlate = state.plate;
    }

    elements.lastPlate.textContent =
        state.plate ? `Placa: ${state.plate}` : "";
}

async function fetchCurrentState() {
    try {
        const res = await fetch("/api/current");
        const state = await res.json();
        updateDisplay(state);
    } catch (err) {
        console.warn("Error polling:", err);
    }
}

async function lookupPlate(plate) {
    if (!plate.trim()) return;
    try {
        const res = await fetch(`/api/lookup/${encodeURIComponent(plate.trim())}`);
        const data = await res.json();
        updateDisplay({
            type: data.found ? "returning" : "new",
            message: data.message,
            plate: plate.trim(),
            customer: data.customer,
        });
    } catch (err) {
        console.error("Error lookup:", err);
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
        console.error("Error set plate:", err);
    }
}

async function simulateArrival() {
    try {
        const res = await fetch("/api/simulate-arrival");
        const state = await res.json();
        updateDisplay(state);
    } catch (err) {
        console.error("Error simulate:", err);
    }
}

// Event listeners
elements.btnLookup.addEventListener("click", () => {
    const plate = elements.plateInput.value;
    if (plate.trim()) {
        setPlateOnServer(plate);
    }
});

elements.plateInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
        const plate = elements.plateInput.value;
        if (plate.trim()) setPlateOnServer(plate);
    }
});

elements.btnSimulate.addEventListener("click", simulateArrival);

// Polling
fetchCurrentState();
setInterval(fetchCurrentState, POLL_INTERVAL_MS);
