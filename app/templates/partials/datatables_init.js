/**
 * Reusable DataTables initialization function
 * 
 * @param {string|Object} config - Either a table ID string or a configuration object
 * @param {Object} options - Optional configuration overrides
 * @param {boolean} options.enableFilters - Enable custom filters (default: false)
 * @param {Object} options.filterConfig - Filter configuration (only used if enableFilters is true)
 * 
 * Configuration object format:
 * {
 *   tableId: 'tableId',
 *   order: [[0, 'desc']],
 *   pageLength: 25,
 *   lengthMenu: [[10, 25, 50, 100], [10, 25, 50, 100]],
 *   responsive: true,
 *   columnDefs: [],
 *   enableFilters: false,
 *   filterConfig: {}
 * }
 */
function initDataTable(config, options) {
    options = options || {};
    
    let tableId, tableConfig;
    
    // Handle both string (tableId) and object (config) formats
    if (typeof config === 'string') {
        tableId = config;
        tableConfig = {
            responsive: true,
            pageLength: 50,
            lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]],
            searching: true,
            autoWidth: false,
            scrollX: false
        };
    } else {
        tableId = config.tableId;
        tableConfig = {
            responsive: config.responsive !== undefined ? config.responsive : true,
            pageLength: config.pageLength || 50,
            lengthMenu: config.lengthMenu || [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]],
            searching: config.searching !== undefined ? config.searching : true,
            autoWidth: config.autoWidth !== undefined ? config.autoWidth : false,
            scrollX: config.scrollX !== undefined ? config.scrollX : false,
            order: config.order,
            columnDefs: config.columnDefs || []
        };
    }
    
    // Apply options overrides
    if (options.order) tableConfig.order = options.order;
    if (options.pageLength) tableConfig.pageLength = options.pageLength;
    if (options.lengthMenu) tableConfig.lengthMenu = options.lengthMenu;
    if (options.responsive !== undefined) tableConfig.responsive = options.responsive;
    if (options.columnDefs) {
        // Merge columnDefs if both exist
        if (tableConfig.columnDefs && tableConfig.columnDefs.length > 0) {
            tableConfig.columnDefs = tableConfig.columnDefs.concat(options.columnDefs);
        } else {
            tableConfig.columnDefs = options.columnDefs;
        }
    }
    if (options.autoWidth !== undefined) tableConfig.autoWidth = options.autoWidth;
    if (options.scrollX !== undefined) tableConfig.scrollX = options.scrollX;
    
    // Initialize the table
    const table = $('#' + tableId).DataTable(tableConfig);
    
    // Handle filters if enabled
    if (options.enableFilters || (typeof config === 'object' && config.enableFilters)) {
        const filterConfig = options.filterConfig || (typeof config === 'object' ? config.filterConfig : {}) || {};
        setupDataTableFilters(tableId, table, filterConfig);
    }
    
    return table;
}

/**
 * Initialize a Risk Reversal table (used by filter system)
 * 
 * @param {HTMLElement} tableElement - The table element
 * @returns {Object|null} - The DataTable instance or null
 */
window.initializeRiskReversalTable = function(tableElement) {
    const tableId = $(tableElement).attr('id');
    if (!tableId) return null;
    
    // Skip if already initialized
    if (window.riskReversalTables[tableId] || $.fn.DataTable.isDataTable('#' + tableId)) {
        if (!window.riskReversalTables[tableId]) {
            window.riskReversalTables[tableId] = $('#' + tableId).DataTable();
        }
        return window.riskReversalTables[tableId];
    }
    
    const table = $(tableElement).DataTable({
        pageLength: 50,
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]],
        order: [[6, 'asc']], // Sort by Net Cost $ ascending
        searching: true,
        responsive: true,
        autoWidth: false,
        scrollX: false,
        columnDefs: [
            {
                targets: 0, // Ratio column
                searchable: true
            },
            {
                targets: 6, // Net Cost $ column - extract numeric value for sorting
                type: 'num',
                render: function(data, type, row) {
                    if (type === 'sort' || type === 'type') {
                        // Extract numeric value from the cell content (handle HTML safely)
                        var text = '';
                        if (typeof data === 'string' && data.trim().startsWith('<')) {
                            // It's HTML, extract text safely
                            var tempDiv = document.createElement('div');
                            tempDiv.innerHTML = data;
                            text = tempDiv.textContent || tempDiv.innerText || data;
                        } else {
                            // Already plain text
                            text = String(data || '');
                        }
                        var match = text.match(/-?\$?([\d.]+)/);
                        if (match) {
                            var value = parseFloat(match[1]);
                            return text.indexOf('-') !== -1 ? -value : value;
                        }
                        return 0;
                    }
                    return data;
                }
            }
        ]
    });
    
    window.riskReversalTables[tableId] = table;
    
    // Apply initial filter (1:1 selected by default) and maintain Net Cost $ ascending sort
    table.column(0).search('^1\\:1$', true, false);
    table.order([[6, 'asc']]).draw();
    
    return table;
};

/**
 * Setup custom filters for DataTables
 * Currently supports ratio filters for Risk Reversal tables
 * 
 * @param {string} tableId - The table ID
 * @param {Object} table - The DataTable instance
 * @param {Object} filterConfig - Filter configuration
 */
function setupDataTableFilters(tableId, table, filterConfig) {
    if (filterConfig.type === 'ratio') {
        // Initialize filter storage
        window.riskReversalTables = window.riskReversalTables || {};
        window.riskReversalSearchFunctions = window.riskReversalSearchFunctions || {};
        window.riskReversalTables[tableId] = table;
        
        // Handle ratio filter changes
        $(document).on('change', 'input[name="ratioFilter"]', function() {
            const selectedRatio = $(this).val();
            
            // Process all risk reversal tables
            $('.risk-reversal-table').each(function() {
                const tableElement = this;
                const currentTableId = $(tableElement).attr('id');
                if (!currentTableId) return;
                
                // Initialize table if needed
                let currentTable = window.riskReversalTables && window.riskReversalTables[currentTableId];
                if (!currentTable) {
                    currentTable = window.initializeRiskReversalTable(tableElement);
                }
                
                if (currentTable) {
                    // Remove any existing custom search function for this table
                    if (window.riskReversalSearchFunctions[currentTableId]) {
                        const existingFunction = window.riskReversalSearchFunctions[currentTableId];
                        const index = $.fn.dataTable.ext.search.indexOf(existingFunction);
                        if (index !== -1) {
                            $.fn.dataTable.ext.search.splice(index, 1);
                        }
                        delete window.riskReversalSearchFunctions[currentTableId];
                    }
                    
                    // Clear any existing column search
                    currentTable.column(0).search('');
                    
                    if (selectedRatio === 'all') {
                        // Show all rows - no custom filter needed
                        currentTable.draw();
                    } else {
                        // Create a custom search function for this specific table
                        const searchFunction = function(settings, data, dataIndex) {
                            // Only apply to this specific table
                            if (settings.nTable.id !== currentTableId) {
                                return true;
                            }
                            
                            // Get the ratio value from the first column (index 0)
                            const ratioValue = data[0];
                            
                            // Extract text content safely (handle HTML)
                            let ratioText = '';
                            if (typeof ratioValue === 'string') {
                                // Check if it's HTML
                                if (ratioValue.trim().startsWith('<')) {
                                    const tempDiv = document.createElement('div');
                                    tempDiv.innerHTML = ratioValue;
                                    ratioText = (tempDiv.textContent || tempDiv.innerText || '').trim();
                                } else {
                                    ratioText = ratioValue.trim();
                                }
                            } else {
                                ratioText = String(ratioValue || '').trim();
                            }
                            
                            // Match the selected ratio
                            return ratioText === selectedRatio;
                        };
                        
                        // Store the function so we can remove it later
                        window.riskReversalSearchFunctions[currentTableId] = searchFunction;
                        
                        // Add the custom search function
                        $.fn.dataTable.ext.search.push(searchFunction);
                        
                        // Redraw the table
                        currentTable.draw();
                    }
                    
                    // Maintain Net Cost $ ascending sort after filter
                    currentTable.order([[6, 'asc']]).draw();
                }
            });
        });
        
        // Also initialize tables when Risk Reversal tab is shown
        $('#risk-reversal-tab').on('shown.bs.tab', function() {
            setTimeout(function() {
                $('.risk-reversal-table').each(function() {
                    window.initializeRiskReversalTable(this);
                });
            }, 100);
        });
        
        // Also try to initialize tables when filter buttons are first clicked
        $(document).on('click', 'input[name="ratioFilter"]', function() {
            setTimeout(function() {
                $('.risk-reversal-table').each(function() {
                    const currentTableId = $(this).attr('id');
                    if (currentTableId && !window.riskReversalTables[currentTableId] && !$.fn.DataTable.isDataTable('#' + currentTableId)) {
                        window.initializeRiskReversalTable(this);
                    }
                });
            }, 50);
        });
    }
}
