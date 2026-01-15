function initTabulatorFromTable(tableId, options = {}) {
  const table = document.getElementById(tableId);
  if (!table) {
    return null;
  }

  const tabulatorId = options.tabulatorId || `${tableId}Tabulator`;
  const container = document.getElementById(tabulatorId);
  if (!container) {
    return null;
  }

  const headers = Array.from(table.querySelectorAll("thead th")).map((th) =>
    th.textContent.trim()
  );
  const rows = Array.from(table.querySelectorAll("tbody tr"));

  const data = rows.map((row) => {
    const cells = Array.from(row.children);
    const rowData = {};
    headers.forEach((header, idx) => {
      const cell = cells[idx];
      const text = cell ? cell.innerText.trim() : "";
      const html = cell ? cell.innerHTML.trim() : "";
      rowData[header] = text;
      rowData[`${header}__html`] = html || text;
    });
    return rowData;
  });

  const columnOverrides = options.columnOverrides || {};

  const columns = headers.map((header) => {
    const override = columnOverrides[header] || {};
    const sampleValue = data.length ? data[0][header] : "";
    const isNumber = sampleValue !== "" && !isNaN(Number(sampleValue));

    return {
      title: header,
      field: header,
      sorter: isNumber ? "number" : "string",
      formatter: (cell) => {
        const rowData = cell.getRow().getData();
        return rowData[`${header}__html`] || cell.getValue();
      },
      ...override,
    };
  });

  const tabulator = new Tabulator(container, {
    data,
    columns,
    layout: "fitColumns",
    pagination: "local",
    paginationSize: options.pageSize || 25,
    initialSort: options.initialSort || [],
  });

  table.style.display = "none";
  return tabulator;
}
