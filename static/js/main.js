/**
 * AA Report Dashboard - Main JavaScript
 * ======================================
 */

// Document ready
$(document).ready(function() {
    console.log('AA Report Dashboard initialized');
    
    // Initialize tooltips
    initTooltips();
    
    // Add table row click handlers
    addTableClickHandlers();
    
    // Format numbers
    formatNumbers();
});

/**
 * Initialize Bootstrap tooltips
 */
function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

/**
 * Add click handlers to table rows
 */
function addTableClickHandlers() {
    // Make table rows clickable (except action buttons)
    $('table tbody tr').on('click', function(e) {
        // Don't trigger if clicking on a button or link
        if ($(e.target).is('a, button') || $(e.target).closest('a, button').length) {
            return;
        }
        
        // Find the view button and click it
        const viewBtn = $(this).find('a[href^="/cluster/"], a[href^="/run/"]').first();
        if (viewBtn.length) {
            window.location.href = viewBtn.attr('href');
        }
    });
}

/**
 * Format numbers with thousand separators
 */
function formatNumbers() {
    $('.format-number').each(function() {
        const num = parseFloat($(this).text());
        if (!isNaN(num)) {
            $(this).text(num.toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }));
        }
    });
}

/**
 * Copy text to clipboard
 */
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        showToast('Copied to clipboard!', 'success');
    }, function(err) {
        showToast('Failed to copy: ' + err, 'danger');
    });
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    const toastHtml = `
        <div class="toast align-items-center text-white bg-${type} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    
    // Create toast container if it doesn't exist
    if ($('#toastContainer').length === 0) {
        $('body').append('<div id="toastContainer" class="toast-container position-fixed top-0 end-0 p-3"></div>');
    }
    
    const $toast = $(toastHtml);
    $('#toastContainer').append($toast);
    
    const toast = new bootstrap.Toast($toast[0]);
    toast.show();
    
    // Remove toast element after it's hidden
    $toast.on('hidden.bs.toast', function() {
        $(this).remove();
    });
}

/**
 * Export table to CSV
 */
function exportTableToCSV(tableId, filename) {
    const table = document.getElementById(tableId);
    if (!table) {
        showToast('Table not found', 'danger');
        return;
    }
    
    let csv = [];
    const rows = table.querySelectorAll('tr');
    
    for (let i = 0; i < rows.length; i++) {
        const row = [];
        const cols = rows[i].querySelectorAll('td, th');
        
        for (let j = 0; j < cols.length; j++) {
            // Skip action columns
            if (cols[j].textContent.trim() === 'Actions' || cols[j].textContent.trim() === 'Action') {
                continue;
            }
            row.push('"' + cols[j].textContent.trim().replace(/"/g, '""') + '"');
        }
        
        csv.push(row.join(','));
    }
    
    // Download CSV
    const csvContent = csv.join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showToast('CSV exported successfully!', 'success');
}

/**
 * Refresh page data
 */
function refreshData() {
    showToast('Refreshing data...', 'info');
    location.reload();
}

/**
 * Format currency
 */
function formatCurrency(amount) {
    return '$' + parseFloat(amount).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

/**
 * Format percentage
 */
function formatPercentage(value) {
    return parseFloat(value).toFixed(1) + '%';
}

/**
 * Debounce function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Add copy button to code blocks
 */
function addCopyButtons() {
    $('code').each(function() {
        const $code = $(this);
        const text = $code.text();
        
        const $copyBtn = $('<button class="btn btn-sm btn-outline-secondary ms-2" title="Copy to clipboard">')
            .html('<i class="bi bi-clipboard"></i>')
            .on('click', function(e) {
                e.stopPropagation();
                copyToClipboard(text);
            });
        
        $code.after($copyBtn);
    });
}

// Global error handler
window.addEventListener('error', function(e) {
    console.error('Global error:', e.error);
    showToast('An error occurred. Please check the console.', 'danger');
});

// Export functions for use in other scripts
window.AADashboard = {
    copyToClipboard,
    showToast,
    exportTableToCSV,
    refreshData,
    formatCurrency,
    formatPercentage
};

