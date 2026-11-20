(() => {
  const board = document.querySelector("#home-kanban");
  if (!board) return;

  const announcement = document.querySelector("#board-announcement");
  let draggedCard = null;
  let originColumn = null;
  let originNextSibling = null;

  const refreshCounts = () => {
    board.querySelectorAll(".board-column").forEach((column) => {
      const count = column.querySelectorAll(".kanban-card").length;
      column.querySelector(".column-count").textContent = count;
      const empty = column.querySelector(".column-empty");
      if (empty) empty.hidden = count > 0;
    });
  };

  board.querySelectorAll(".kanban-card").forEach((card) => {
    card.addEventListener("dragstart", (event) => {
      draggedCard = card;
      originColumn = card.closest(".column-cards");
      originNextSibling = card.nextElementSibling;
      card.classList.add("is-dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", card.dataset.taskId);
    });

    card.addEventListener("dragend", () => {
      card.classList.remove("is-dragging");
      board.querySelectorAll(".is-drop-target").forEach((column) => column.classList.remove("is-drop-target"));
      draggedCard = null;
    });
  });

  board.querySelectorAll(".board-column").forEach((column) => {
    column.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      board.querySelectorAll(".is-drop-target").forEach((item) => item.classList.remove("is-drop-target"));
      column.classList.add("is-drop-target");
    });

    column.addEventListener("dragleave", (event) => {
      if (!column.contains(event.relatedTarget)) column.classList.remove("is-drop-target");
    });

    column.addEventListener("drop", async (event) => {
      event.preventDefault();
      column.classList.remove("is-drop-target");
      const cardId = event.dataTransfer.getData("text/plain");
      if (!draggedCard || draggedCard.dataset.taskId !== cardId) return;

      const card = draggedCard;
      const sourceColumn = originColumn;
      const sourceNextSibling = originNextSibling;
      const destination = column.querySelector(".column-cards");
      const oldStatus = card.closest(".board-column").dataset.status;
      const newStatus = column.dataset.status;
      if (oldStatus === newStatus) return;

      destination.append(card);
      refreshCounts();
      const form = card.querySelector(".card-move-form");
      const statusSelect = form.querySelector('select[name="status"]');
      statusSelect.value = newStatus;
      card.classList.add("is-saving");

      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        if (!response.ok) throw new Error("Task update failed");
        const result = await response.json();
        if (result.status !== newStatus) throw new Error("Unexpected status response");
        card.classList.remove("is-saving");
        announcement.textContent = `کارت به ستون «${column.dataset.label}» منتقل شد.`;
      } catch (_error) {
        if (sourceColumn) {
          if (sourceNextSibling && sourceNextSibling.parentElement === sourceColumn) {
            sourceColumn.insertBefore(card, sourceNextSibling);
          } else {
            sourceColumn.append(card);
          }
        }
        statusSelect.value = oldStatus;
        card.classList.remove("is-saving");
        refreshCounts();
        announcement.textContent = "ذخیره‌ی وضعیت انجام نشد؛ کارت به ستون قبلی برگشت.";
      }
    });
  });
})();
