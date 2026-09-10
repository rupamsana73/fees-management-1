document.addEventListener("DOMContentLoaded", () => {
    const sidebar = document.querySelector("[data-sidebar]");
    const backdrop = document.querySelector("[data-sidebar-backdrop]");
    const toggle = document.querySelector("[data-sidebar-toggle]");

    const closeSidebar = () => {
        sidebar?.classList.remove("is-open");
        backdrop?.classList.remove("is-visible");
    };

    toggle?.addEventListener("click", () => {
        sidebar?.classList.toggle("is-open");
        backdrop?.classList.toggle("is-visible");
    });
    backdrop?.addEventListener("click", closeSidebar);

    const searchInput = document.querySelector("[data-table-search]");
    const tableRows = [...document.querySelectorAll("[data-student-row]")];
    searchInput?.addEventListener("input", () => {
        const query = searchInput.value.trim().toLowerCase();
        tableRows.forEach((row) => {
            row.hidden = !row.textContent.toLowerCase().includes(query);
        });
    });

    const studentSelect = document.getElementById("id_student");
    const amountInput = document.getElementById("id_amount_paid");
    const pendingPreview = document.querySelector("[data-pending-preview]");
    const updatePendingPreview = () => {
        const selected = studentSelect?.selectedOptions[0];
        const pending = Number(selected?.dataset.pending);
        const amount = Number(amountInput?.value || 0);
        if (!selected?.value || Number.isNaN(pending)) {
            if (pendingPreview) pendingPreview.textContent = "—";
            return;
        }
        if (pendingPreview) pendingPreview.textContent = Math.max(pending - amount, 0).toFixed(2);
    };
    studentSelect?.addEventListener("change", updatePendingPreview);
    amountInput?.addEventListener("input", updatePendingPreview);

    document.querySelectorAll(".reminder-button").forEach((button) => {
        button.addEventListener("click", () => {
            button.innerHTML = '<i class="bi bi-check2"></i> Reminder queued';
            button.classList.add("text-success");
            button.disabled = true;
        });
    });

    document.querySelectorAll("[data-sort-table]").forEach((table) => {
        const headers = [...table.querySelectorAll("th[data-sort-key]")];
        headers.forEach((header) => {
            header.addEventListener("click", () => {
                const index = headers.indexOf(header);
                const direction = header.dataset.sortDirection === "asc" ? -1 : 1;
                headers.forEach((item) => { item.dataset.sortDirection = ""; });
                header.dataset.sortDirection = direction === 1 ? "asc" : "desc";
                const body = table.tBodies[0];
                [...body.rows].sort((a, b) => {
                    const first = a.cells[index].dataset.sortValue || a.cells[index].textContent.trim();
                    const second = b.cells[index].dataset.sortValue || b.cells[index].textContent.trim();
                    const numericFirst = Number(first);
                    const numericSecond = Number(second);
                    if (!Number.isNaN(numericFirst) && !Number.isNaN(numericSecond)) {
                        return (numericFirst - numericSecond) * direction;
                    }
                    return first.localeCompare(second) * direction;
                }).forEach((row) => body.appendChild(row));
            });
        });
    });

    const chartCanvas = document.getElementById("collectionChart");
    if (chartCanvas && window.Chart) {
        const labelsElement = document.getElementById("month-labels");
        const valuesElement = document.getElementById("month-values");
        const labels = labelsElement ? JSON.parse(labelsElement.textContent) : [];
        const values = valuesElement ? JSON.parse(valuesElement.textContent).map(Number) : [];
        new Chart(chartCanvas, {
            type: "bar",
            data: { labels, datasets: [{ data: values, backgroundColor: "#5b5ce2", borderRadius: 6, maxBarThickness: 38 }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { color: "#8a92a5", font: { family: "Inter" } } }, y: { beginAtZero: true, grid: { color: "#edf0f5" }, ticks: { color: "#8a92a5", callback: (value) => value.toLocaleString() } } } }
        });
    }
});
