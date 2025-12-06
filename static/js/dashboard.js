// Personal Finance Manager - Dashboard JavaScript
// Clean, simple, and working version

// Global variables
let charts = {
    trend: null,
    category: null,
    monthlyReport: null,
    categoryReport: null,
    categoryIncome: null,
    categoryExpense: null,
    yearlyReport: null,
    cashFlowReport: null,
    topSpendingReport: null,
    forecastReport: null
};
let currentCategories = [];
let paymentMethods = [];
let currentTransactionId = null;
let allTransactions = [];
let activeFilters = {
    description: '',
    categories: [],
    paymentMethods: [],
    types: [],
    statuses: [],
    minAmount: null,
    maxAmount: null,
    startDate: null,
    endDate: null,
    notes: ''
};
let reportFiltersInitialized = false;
let filterDropdownsInitialized = false;
let loadedReportTabs = new Set(); // Track which report tabs have been loaded
let reportTabsInitialized = false; // Track if tab listeners are initialized

// Geolocation helper function
function getGeolocation() {
    return new Promise((resolve) => {
        // Check if geolocation is supported
        if (!navigator.geolocation) {
            console.log('Geolocation is not supported by this browser');
            resolve(null);
            return;
        }

        // Get current position with timeout
        navigator.geolocation.getCurrentPosition(
            (position) => {
                // Success callback
                const location = {
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                    accuracy: position.coords.accuracy
                };
                console.log('Geolocation captured:', location);
                resolve(location);
            },
            (error) => {
                // Error callback - don't block the transaction
                console.log('Geolocation error:', error.message);
                resolve(null);
            },
            {
                // Options
                enableHighAccuracy: true,
                timeout: 5000, // 5 seconds timeout
                maximumAge: 0 // Don't use cached position
            }
        );
    });
}

// Initialize everything when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('=== Dashboard Loading ===');
    initApp();
});

// Main initialization function
function initApp() {
    try {
        // 1. Setup navigation
        setupNavigation();

        // 2. Setup form buttons
        setupFormButtons();

        // 3. Load initial data
        loadCategories();
        loadPaymentMethods();
        populateDateSelectors();

        // 4. Initialize charts
        initCharts();

        // 5. Load default page (transactions)
        navigateToPage('transactions');

        console.log('✓ Dashboard loaded successfully');
    } catch (error) {
        console.error('✗ Dashboard initialization failed:', error);
    }
}

// ================================
// NAVIGATION
// ================================

function setupNavigation() {
    const navLinks = document.querySelectorAll('.sidebar .nav-link');
    console.log('Setting up navigation for', navLinks.length, 'links');

    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const pageName = this.getAttribute('data-page');
            navigateToPage(pageName);
        });
    });

    // Setup refresh button - recalculate balances and reload
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', recalculateAndRefresh);
    }
}

function navigateToPage(pageName) {
    console.log('→ Navigating to:', pageName);

    // Hide all pages
    const allPages = document.querySelectorAll('.page-content');
    allPages.forEach(page => page.style.display = 'none');

    // Remove active from all nav links
    const allLinks = document.querySelectorAll('.sidebar .nav-link');
    allLinks.forEach(link => link.classList.remove('active'));

    // Show target page
    const targetPage = document.getElementById(pageName + 'Page');
    if (targetPage) {
        targetPage.style.display = 'block';
        console.log('✓ Showing:', pageName + 'Page');
    } else {
        console.error('✗ Page not found:', pageName + 'Page');
        return;
    }

    // Set active nav link
    const activeLink = document.querySelector(`[data-page="${pageName}"]`);
    if (activeLink) {
        activeLink.classList.add('active');
    }

    // Load page-specific data
    loadPageData(pageName);
}

function loadPageData(pageName) {
    switch(pageName) {
        case 'transactions':
            loadTransactions();
            break;
        case 'reports':
            loadReports();
            break;
        case 'overview':
            loadDashboardStats();
            break;
        case 'tax':
            loadTaxCalculator();
            break;
    }
}

// ================================
// FORM BUTTONS
// ================================

function setupFormButtons() {
    // Transaction form - prevent default form submission
    const transForm = document.getElementById('transactionForm');
    if (transForm) {
        transForm.addEventListener('submit', function(e) {
            e.preventDefault();
            saveTransaction();
        });
    }

    // Transaction form
    const saveTransBtn = document.getElementById('saveTransactionBtn');
    if (saveTransBtn) {
        saveTransBtn.addEventListener('click', function(e) {
            e.preventDefault();
            saveTransaction();
        });
    }

    // Month navigation buttons
    const prevMonthBtn = document.getElementById('prevMonthBtn');
    if (prevMonthBtn) {
        prevMonthBtn.addEventListener('click', navigateToPreviousMonth);
    }

    const nextMonthBtn = document.getElementById('nextMonthBtn');
    if (nextMonthBtn) {
        nextMonthBtn.addEventListener('click', navigateToNextMonth);
    }

    // Auto-load transactions when month/year changes
    const monthYearPicker = document.getElementById('monthYearPicker');
    if (monthYearPicker) {
        // Use both 'change' and 'input' events for better browser compatibility
        monthYearPicker.addEventListener('change', () => {
            console.log('Month picker changed to:', monthYearPicker.value);
            loadTransactions();
        });
        monthYearPicker.addEventListener('input', () => {
            console.log('Month picker input:', monthYearPicker.value);
        });
    }

    const viewPaymentTotalsBtn = document.getElementById('viewPaymentTotalsBtn');
    if (viewPaymentTotalsBtn) {
        viewPaymentTotalsBtn.addEventListener('click', loadPaymentTotals);
    }

    // Set today's date in transaction form
    const transDate = document.getElementById('transDate');
    if (transDate) {
        transDate.value = new Date().toISOString().split('T')[0];
    }

    // Credit card management
    const addCardBtn = document.getElementById('addCreditCardBtn');
    if (addCardBtn) {
        addCardBtn.addEventListener('click', showAddCreditCardForm);
    }

    const cancelAddCardBtn = document.getElementById('cancelAddCardBtn');
    if (cancelAddCardBtn) {
        cancelAddCardBtn.addEventListener('click', hideAddCreditCardForm);
    }

    const creditCardForm = document.getElementById('creditCardForm');
    if (creditCardForm) {
        creditCardForm.addEventListener('submit', saveCreditCard);
    }

    // Filter buttons
    const applyFiltersBtn = document.getElementById('applyFiltersBtn');
    if (applyFiltersBtn) {
        applyFiltersBtn.addEventListener('click', applyFilters);
    }

    // Clear filters button in modal
    const clearFiltersBtn = document.getElementById('clearFiltersBtn');
    if (clearFiltersBtn) {
        clearFiltersBtn.addEventListener('click', clearFilters);
    }

    // Clear filters button on page
    const clearFiltersPageBtn = document.getElementById('clearFiltersPageBtn');
    if (clearFiltersPageBtn) {
        clearFiltersPageBtn.addEventListener('click', clearFilters);
    }

    // Setup filter modal to populate checkboxes when shown
    const filterModal = document.getElementById('filterModal');
    if (filterModal) {
        filterModal.addEventListener('shown.bs.modal', populateFilterDropdowns);
    }

    // Setup manage categories modal to load categories when shown
    const manageCategoriesModal = document.getElementById('manageCategoriesModal');
    if (manageCategoriesModal) {
        manageCategoriesModal.addEventListener('shown.bs.modal', loadCategoriesForManagement);
    }

    // New category inline creation
    const toggleNewCategoryBtn = document.getElementById('toggleNewCategoryBtn');
    if (toggleNewCategoryBtn) {
        toggleNewCategoryBtn.addEventListener('click', toggleNewCategoryForm);
    }

    const saveNewCategoryBtn = document.getElementById('saveNewCategoryBtn');
    if (saveNewCategoryBtn) {
        saveNewCategoryBtn.addEventListener('click', saveNewCategory);
    }

    const cancelNewCategoryBtn = document.getElementById('cancelNewCategoryBtn');
    if (cancelNewCategoryBtn) {
        cancelNewCategoryBtn.addEventListener('click', hideNewCategoryForm);
    }

    // Allow pressing Enter to save new category
    const newCategoryName = document.getElementById('newCategoryName');
    if (newCategoryName) {
        newCategoryName.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                saveNewCategory();
            }
        });
    }

    // Category edit form buttons
    const saveEditCategoryBtn = document.getElementById('saveEditCategoryBtn');
    if (saveEditCategoryBtn) {
        saveEditCategoryBtn.addEventListener('click', saveEditCategory);
    }

    const cancelEditCategoryBtn = document.getElementById('cancelEditCategoryBtn');
    if (cancelEditCategoryBtn) {
        cancelEditCategoryBtn.addEventListener('click', hideEditCategoryForm);
    }

    // Delete category confirmation
    const confirmDeleteCategoryBtn = document.getElementById('confirmDeleteCategoryBtn');
    if (confirmDeleteCategoryBtn) {
        confirmDeleteCategoryBtn.addEventListener('click', deleteCategory);
    }
}

// ================================
// CATEGORIES
// ================================

function loadCategories() {
    return fetch('/api/categories')
        .then(response => response.json())
        .then(data => {
            currentCategories = data;
            populateCategoryDropdowns(data);
            return data;
        })
        .catch(error => {
            console.error('Error loading categories:', error);
            throw error;
        });
}

function populateCategoryDropdowns(categories) {
    const dropdowns = ['transCategory', 'recCategory'];

    dropdowns.forEach(dropdownId => {
        const dropdown = document.getElementById(dropdownId);
        if (dropdown) {
            dropdown.innerHTML = '<option value="">Select Category</option>';
            categories.forEach(cat => {
                dropdown.innerHTML += `<option value="${cat.id}">${cat.name} (${cat.type})</option>`;
            });
        }
    });

    // Also populate filter dropdown
    const filterDropdown = document.getElementById('filterCategory');
    if (filterDropdown) {
        filterDropdown.innerHTML = '<option value="">All Categories</option>';
        categories.forEach(cat => {
            filterDropdown.innerHTML += `<option value="${cat.id}">${cat.name} (${cat.type})</option>`;
        });
    }
}

function toggleNewCategoryForm() {
    const form = document.getElementById('newCategoryForm');
    if (form) {
        if (form.style.display === 'none') {
            showNewCategoryForm();
        } else {
            hideNewCategoryForm();
        }
    }
}

function showNewCategoryForm() {
    const form = document.getElementById('newCategoryForm');
    const message = document.getElementById('newCategoryMessage');

    if (form) {
        form.style.display = 'block';
        // Clear previous values
        document.getElementById('newCategoryName').value = '';
        document.getElementById('newCategoryType').value = '';
        if (message) {
            message.style.display = 'none';
        }
        // Focus on name input
        document.getElementById('newCategoryName').focus();
    }
}

function hideNewCategoryForm() {
    const form = document.getElementById('newCategoryForm');
    if (form) {
        form.style.display = 'none';
        // Clear form
        document.getElementById('newCategoryName').value = '';
        document.getElementById('newCategoryType').value = '';
        const message = document.getElementById('newCategoryMessage');
        if (message) {
            message.style.display = 'none';
        }
    }
}

function saveNewCategory() {
    const nameInput = document.getElementById('newCategoryName');
    const typeInput = document.getElementById('newCategoryType');
    const message = document.getElementById('newCategoryMessage');
    const saveBtn = document.getElementById('saveNewCategoryBtn');

    const name = nameInput.value.trim();
    const type = typeInput.value;

    // Validate inputs
    if (!name) {
        showCategoryMessage('Please enter a category name', 'danger');
        return;
    }

    if (!type) {
        showCategoryMessage('Please select a category type', 'danger');
        return;
    }

    // Disable button during save
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Saving...';

    // Send to API
    fetch('/api/categories', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            name: name,
            type: type
        })
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => {
                throw new Error(err.error || 'Failed to create category');
            });
        }
        return response.json();
    })
    .then(newCategory => {
        // Success!
        showCategoryMessage('Category created successfully!', 'success');

        // Reload categories to update all dropdowns, then select the new category
        loadCategories().then(() => {
            // Hide form after a brief delay to show success message
            setTimeout(() => {
                hideNewCategoryForm();
            }, 800);

            // Select the newly created category in the dropdown
            const transCategorySelect = document.getElementById('transCategory');
            if (transCategorySelect) {
                transCategorySelect.value = newCategory.id;
            }
        }).catch(error => {
            console.error('Error reloading categories:', error);
        });
    })
    .catch(error => {
        console.error('Error creating category:', error);
        showCategoryMessage(error.message || 'Failed to create category', 'danger');
    })
    .finally(() => {
        // Re-enable button
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<i class="fas fa-check me-1"></i>Save';
    });
}

function showCategoryMessage(text, type) {
    const message = document.getElementById('newCategoryMessage');
    if (message) {
        message.className = `alert alert-${type} mb-0`;
        message.style.fontSize = '0.875rem';
        message.style.padding = '0.5rem';
        message.textContent = text;
        message.style.display = 'block';
    }
}

function loadCategoriesForManagement() {
    const incomeList = document.getElementById('incomeCategoriesList');
    const expenseList = document.getElementById('expenseCategoriesList');

    if (!incomeList || !expenseList) return;

    // Hide edit form when reloading categories
    hideEditCategoryForm();

    // Show loading state
    incomeList.innerHTML = '<div class="text-center p-3"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';
    expenseList.innerHTML = '<div class="text-center p-3"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';

    fetch('/api/categories')
        .then(response => response.json())
        .then(categories => {
            // Separate categories by type
            const incomeCategories = categories.filter(cat => cat.type === 'income');
            const expenseCategories = categories.filter(cat => cat.type === 'expense');

            // Display income categories
            if (incomeCategories.length > 0) {
                incomeList.innerHTML = incomeCategories.map(cat => `
                    <div class="list-group-item d-flex justify-content-between align-items-center">
                        <span><i class="fas fa-tag me-2"></i>${cat.name}</span>
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-outline-primary" onclick="editCategory(${cat.id}, '${cat.name.replace(/'/g, "\\'")}', '${cat.type}')" title="Edit">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-outline-danger" onclick="showDeleteCategoryConfirm(${cat.id}, '${cat.name.replace(/'/g, "\\'")}')">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                `).join('');
            } else {
                incomeList.innerHTML = '<div class="opacity-75 text-center p-3">No income categories</div>';
            }

            // Display expense categories
            if (expenseCategories.length > 0) {
                expenseList.innerHTML = expenseCategories.map(cat => `
                    <div class="list-group-item d-flex justify-content-between align-items-center">
                        <span><i class="fas fa-tag me-2"></i>${cat.name}</span>
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-outline-primary" onclick="editCategory(${cat.id}, '${cat.name.replace(/'/g, "\\'")}', '${cat.type}')" title="Edit">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-outline-danger" onclick="showDeleteCategoryConfirm(${cat.id}, '${cat.name.replace(/'/g, "\\'")}')">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                `).join('');
            } else {
                expenseList.innerHTML = '<div class="opacity-75 text-center p-3">No expense categories</div>';
            }
        })
        .catch(error => {
            console.error('Error loading categories:', error);
            incomeList.innerHTML = '<div class="alert alert-danger">Failed to load categories</div>';
            expenseList.innerHTML = '<div class="alert alert-danger">Failed to load categories</div>';
        });
}

let categoryToDelete = null;

function showDeleteCategoryConfirm(categoryId, categoryName) {
    categoryToDelete = categoryId;
    const message = document.getElementById('deleteCategoryConfirmMessage');
    if (message) {
        message.textContent = `Are you sure you want to delete the category "${categoryName}"?`;
    }

    const modal = new bootstrap.Modal(document.getElementById('deleteCategoryConfirmModal'));
    modal.show();
}

function deleteCategory() {
    if (!categoryToDelete) return;

    const categoryId = categoryToDelete;
    categoryToDelete = null;

    // Close confirmation modal
    const confirmModal = bootstrap.Modal.getInstance(document.getElementById('deleteCategoryConfirmModal'));
    if (confirmModal) {
        confirmModal.hide();
    }

    fetch(`/api/categories/${categoryId}`, {
        method: 'DELETE'
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => {
                throw new Error(err.error || 'Failed to delete category');
            });
        }
        return response.json();
    })
    .then(result => {
        // Success!
        showToast('Category deleted successfully', 'success');

        // Reload categories in the management modal
        loadCategoriesForManagement();

        // Reload categories in all dropdowns
        loadCategories();
    })
    .catch(error => {
        console.error('Error deleting category:', error);
        showToast(error.message || 'Failed to delete category', 'danger');
    });
}

function editCategory(categoryId, categoryName, categoryType) {
    // Show edit form
    const editForm = document.getElementById('editCategoryForm');
    if (editForm) {
        editForm.style.display = 'block';
    }

    // Populate form fields
    document.getElementById('editCategoryId').value = categoryId;
    document.getElementById('editCategoryName').value = categoryName;
    document.getElementById('editCategoryType').value = categoryType;

    // Hide message
    const message = document.getElementById('editCategoryMessage');
    if (message) {
        message.style.display = 'none';
    }

    // Scroll to edit form
    editForm.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function hideEditCategoryForm() {
    const editForm = document.getElementById('editCategoryForm');
    if (editForm) {
        editForm.style.display = 'none';
    }

    // Clear form
    document.getElementById('editCategoryId').value = '';
    document.getElementById('editCategoryName').value = '';
    document.getElementById('editCategoryType').value = '';

    // Hide message
    const message = document.getElementById('editCategoryMessage');
    if (message) {
        message.style.display = 'none';
    }
}

function saveEditCategory() {
    const categoryId = document.getElementById('editCategoryId').value;
    const name = document.getElementById('editCategoryName').value.trim();
    const type = document.getElementById('editCategoryType').value;
    const saveBtn = document.getElementById('saveEditCategoryBtn');
    const message = document.getElementById('editCategoryMessage');

    // Validate
    if (!name) {
        showEditCategoryMessage('Please enter a category name', 'danger');
        return;
    }

    if (!type) {
        showEditCategoryMessage('Please select a category type', 'danger');
        return;
    }

    // Disable button during save
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Saving...';

    fetch(`/api/categories/${categoryId}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            name: name,
            type: type
        })
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => {
                throw new Error(err.error || 'Failed to update category');
            });
        }
        return response.json();
    })
    .then(updatedCategory => {
        // Success!
        showEditCategoryMessage('Category updated successfully!', 'success');
        showToast('Category updated successfully', 'success');

        // Reload categories in the management modal
        setTimeout(() => {
            loadCategoriesForManagement();
        }, 1000);

        // Reload categories in all dropdowns
        loadCategories();
    })
    .catch(error => {
        console.error('Error updating category:', error);
        showEditCategoryMessage(error.message || 'Failed to update category', 'danger');
    })
    .finally(() => {
        // Re-enable button
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<i class="fas fa-save me-1"></i>Save Changes';
    });
}

function showEditCategoryMessage(text, type) {
    const message = document.getElementById('editCategoryMessage');
    if (message) {
        message.className = `alert alert-${type} mb-0`;
        message.style.fontSize = '0.875rem';
        message.style.padding = '0.5rem';
        message.textContent = text;
        message.style.display = 'block';
    }
}

// ================================
// DASHBOARD / OVERVIEW
// ================================

function loadDashboardStats() {
    showLoading();

    fetch('/api/dashboard-stats')
        .then(response => response.json())
        .then(data => {
            updateStatsCards(data.current_stats);
            updateRecentTransactions(data.recent_transactions);
            updateTrendChart(data.monthly_trend);
            hideLoading();
        })
        .catch(error => {
            console.error('Error loading dashboard stats:', error);
            hideLoading();
        });
}

function updateStatsCards(stats) {
    if (!stats) return;

    // Current Balance
    const balanceEl = document.getElementById('currentBalance');
    if (balanceEl) {
        balanceEl.textContent = formatCurrency(stats.current_balance || 0);
    }

    // Monthly Income
    const incomeEl = document.getElementById('monthlyIncome');
    if (incomeEl) {
        incomeEl.textContent = formatCurrency(stats.total_income || 0);
    }

    // Monthly Expenses
    const expensesEl = document.getElementById('monthlyExpenses');
    if (expensesEl) {
        expensesEl.textContent = formatCurrency(stats.total_expenses || 0);
    }

    // Savings Rate
    const savingsEl = document.getElementById('savingsRate');
    if (savingsEl && stats.total_income > 0) {
        const rate = ((stats.total_income - stats.total_expenses) / stats.total_income * 100).toFixed(1);
        savingsEl.textContent = rate + '%';
    }
}

function updateRecentTransactions(transactions) {
    const tbody = document.querySelector('#recentTransactionsTable tbody');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!transactions || transactions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center">No transactions found</td></tr>';
        return;
    }

    // Calculate running balance for recent transactions
    // Note: transactions come sorted by created_at DESC, so we need to reverse to calculate
    const sortedTransactions = [...transactions].reverse();
    let runningBalance = 0;
    sortedTransactions.forEach(t => {
        const debit = parseFloat(t.debit) || 0;
        const credit = parseFloat(t.credit) || 0;
        runningBalance += debit - credit;
        t.calculatedBalance = runningBalance;
    });

    // Display in original order (newest first)
    sortedTransactions.reverse().forEach(t => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${t.transaction_date ? formatDate(t.transaction_date) : '-'}</td>
            <td>${t.description}</td>
            <td><span class="badge bg-secondary">${t.category || 'Uncategorized'}</span></td>
            <td class="text-success">${t.debit ? formatCurrency(t.debit) : '-'}</td>
            <td class="text-danger">${t.credit ? formatCurrency(t.credit) : '-'}</td>
            <td class="fw-bold">${formatCurrency(t.calculatedBalance)}</td>
        `;
        tbody.appendChild(row);
    });
}

// ================================
// TRANSACTIONS PAGE
// ================================

function loadTransactions(applyActiveFilters = false) {
    // Parse month/year from the month picker (format: YYYY-MM)
    const monthYearPicker = document.getElementById('monthYearPicker');
    let year, month;

    if (monthYearPicker && monthYearPicker.value) {
        const [yearStr, monthStr] = monthYearPicker.value.split('-');
        year = parseInt(yearStr);
        month = parseInt(monthStr);
        console.log('📅 Loading transactions - Picker value:', monthYearPicker.value, '→ Year:', year, 'Month:', month);
    } else {
        year = new Date().getFullYear();
        month = new Date().getMonth() + 1;
        console.log('📅 Loading transactions - Using current date → Year:', year, 'Month:', month);
    }

    showLoading();

    // Build query parameters
    let queryParams = `year=${year}&month=${month}`;
    console.log('🔗 API Query:', `/api/transactions?${queryParams}`);

    // Add filter parameters if requested
    if (applyActiveFilters) {
        // When filters are active, search across all months/years
        queryParams += `&searchAll=true`;

        if (activeFilters.description) {
            queryParams += `&description=${encodeURIComponent(activeFilters.description)}`;
        }
        if (activeFilters.notes) {
            queryParams += `&notes=${encodeURIComponent(activeFilters.notes)}`;
        }
        if (activeFilters.categories.length > 0) {
            queryParams += `&categories=${activeFilters.categories.join(',')}`;
        }
        if (activeFilters.paymentMethods.length > 0) {
            queryParams += `&paymentMethods=${activeFilters.paymentMethods.join(',')}`;
        }
        if (activeFilters.types.length > 0) {
            queryParams += `&types=${activeFilters.types.join(',')}`;
        }
        if (activeFilters.statuses.length > 0) {
            queryParams += `&statuses=${activeFilters.statuses.join(',')}`;
        }
        if (activeFilters.minAmount !== null) {
            queryParams += `&minAmount=${activeFilters.minAmount}`;
        }
        if (activeFilters.maxAmount !== null) {
            queryParams += `&maxAmount=${activeFilters.maxAmount}`;
        }
        if (activeFilters.startDate) {
            queryParams += `&startDate=${activeFilters.startDate}`;
        }
        if (activeFilters.endDate) {
            queryParams += `&endDate=${activeFilters.endDate}`;
        }
    }

    fetch(`/api/transactions?${queryParams}`)
        .then(response => response.json())
        .then(data => {
            console.log('Transactions received:', data);
            allTransactions = data; // Store all transactions globally
            displayTransactions(data); // Display transactions directly
            hideLoading();
        })
        .catch(error => {
            console.error('Error loading transactions:', error);
            hideLoading();
        });
}

function navigateToPreviousMonth() {
    const monthYearPicker = document.getElementById('monthYearPicker');

    if (!monthYearPicker) return;

    // Parse current value (format: YYYY-MM)
    const [yearStr, monthStr] = monthYearPicker.value.split('-');
    let currentMonth = parseInt(monthStr);
    let currentYear = parseInt(yearStr);

    console.log('⬅️ Previous month button - Current:', monthYearPicker.value);

    // Go to previous month
    currentMonth--;

    // If month goes below 1, go to December of previous year
    if (currentMonth < 1) {
        currentMonth = 12;
        currentYear--;
    }

    // Update month picker
    monthYearPicker.value = `${currentYear}-${String(currentMonth).padStart(2, '0')}`;
    console.log('⬅️ Previous month button - New value:', monthYearPicker.value);

    // Load transactions for the new month
    loadTransactions();
}

function navigateToNextMonth() {
    const monthYearPicker = document.getElementById('monthYearPicker');

    if (!monthYearPicker) return;

    // Parse current value (format: YYYY-MM)
    const [yearStr, monthStr] = monthYearPicker.value.split('-');
    let currentMonth = parseInt(monthStr);
    let currentYear = parseInt(yearStr);

    console.log('➡️ Next month button - Current:', monthYearPicker.value);

    // Go to next month
    currentMonth++;

    // If month goes above 12, go to January of next year
    if (currentMonth > 12) {
        currentMonth = 1;
        currentYear++;
    }

    // Update month picker
    monthYearPicker.value = `${currentYear}-${String(currentMonth).padStart(2, '0')}`;
    console.log('➡️ Next month button - New value:', monthYearPicker.value);

    // Load transactions for the new month
    loadTransactions();
}

function recalculateAndRefresh() {
    // Parse month/year from the month picker (format: YYYY-MM)
    const monthYearPicker = document.getElementById('monthYearPicker');
    let year, month;

    if (monthYearPicker && monthYearPicker.value) {
        const [yearStr, monthStr] = monthYearPicker.value.split('-');
        year = parseInt(yearStr);
        month = parseInt(monthStr);
    } else {
        year = new Date().getFullYear();
        month = new Date().getMonth() + 1;
    }

    showLoading();

    // Call recalculate balances API
    fetch('/api/recalculate-balances', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            year: parseInt(year),
            month: parseInt(month)
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            console.error('Recalculation error:', data.error);
            showToast('Error recalculating balances: ' + data.error, 'danger');
            hideLoading();
        } else {
            console.log('Balances recalculated:', data.message);
            showToast(data.message, 'success');
            // Reload transactions to show updated balances
            loadTransactions();
        }
    })
    .catch(error => {
        console.error('Error recalculating balances:', error);
        showToast('Error recalculating balances', 'danger');
        hideLoading();
    });
}

function displayTransactions(transactions) {
    const tbody = document.querySelector('#transactionsTable tbody');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!transactions || transactions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center">No transactions for this period</td></tr>';
        return;
    }

    // Sort transactions by ID (oldest first) to calculate balance correctly
    const sortedTransactions = [...transactions].sort((a, b) => a.id - b.id);

    // Calculate balance for each transaction
    let runningBalance = 0;
    sortedTransactions.forEach(t => {
        const debit = parseFloat(t.debit) || 0;
        const credit = parseFloat(t.credit) || 0;
        runningBalance += debit - credit;
        t.calculatedBalance = runningBalance;
    });

    // Display transactions in reverse order (newest first)
    sortedTransactions.reverse().forEach(t => {
        const row = document.createElement('tr');

        // Checkbox for marking done/undone (handle both boolean and numeric values)
        const isDone = t.is_done === true || t.is_done === 1;
        const checkboxHtml = isDone
            ? `<input type="checkbox" class="form-check-input" checked onchange="unmarkTransaction(${t.id})" title="${t.payment_method_name || 'Done'}">`
            : `<input type="checkbox" class="form-check-input" onchange="showPaymentMethodModal(${t.id})">`;

        // Store transaction data
        row.dataset.transaction = JSON.stringify(t);

        // Apply highlighting class if done
        let rowClass = '';
        if (isDone && t.payment_method_color) {
            rowClass = `class="transaction-highlighted"`;
            row.dataset.paymentColor = t.payment_method_color;
        }

        // Format paid_at date if exists
        const paidAtDisplay = t.paid_at ? formatDate(t.paid_at) : '-';

        row.innerHTML = `
            <td class="text-center">${checkboxHtml}</td>
            <td class="description-cell" style="cursor: pointer;" data-transaction-id="${t.id}">${t.description}</td>
            <td><span class="badge bg-secondary">${t.category_name || 'Uncategorized'}</span></td>
            <td class="text-success">${t.debit ? formatCurrency(t.debit) : '-'}</td>
            <td class="text-danger">${t.credit ? formatCurrency(t.credit) : '-'}</td>
            <td class="fw-bold">${formatCurrency(t.calculatedBalance)}</td>
            <td class="opacity-75 small">${paidAtDisplay}</td>
            <td>${t.notes || '-'}</td>
            <td>
                <button class="btn btn-sm btn-primary me-1" onclick="editTransaction(${t.id})" title="Edit">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn btn-sm btn-danger me-1" onclick="deleteTransaction(${t.id})" title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
                <button class="btn btn-sm btn-warning me-1" onclick="showMoveCopyModal(${t.id}, 'move')" title="Move to Month">
                    <i class="fas fa-arrow-right"></i>
                </button>
                <button class="btn btn-sm btn-success me-1" onclick="showMoveCopyModal(${t.id}, 'copy')" title="Copy to Month">
                    <i class="fas fa-copy"></i>
                </button>
                <button class="btn btn-sm btn-info" onclick="showAuditModal(${t.id})" title="Audit Log">
                    <i class="fas fa-history"></i>
                </button>
            </td>
        `;

        // Get the description cell
        const descCell = row.querySelector('.description-cell');

        // Check if transaction is paid (handle both boolean and numeric values)
        const isPaid = t.is_paid === true || t.is_paid === 1;

        // Apply background color to all cells for proper highlighting
        if (isDone && t.payment_method_color) {
            console.log(`Highlighting transaction ${t.id} with color ${t.payment_method_color}`);
            row.classList.add('transaction-highlighted');
            const cells = row.querySelectorAll('td');
            cells.forEach((cell, index) => {
                // Apply to all cells except description (index 1)
                if (index !== 1) {
                    cell.style.backgroundColor = t.payment_method_color;
                } else {
                    // Apply to description cell only if is_paid is true
                    if (isPaid) {
                        cell.style.backgroundColor = t.payment_method_color;
                    }
                }
            });
        }

        // Add click handler to description cell
        if (descCell) {
            // Store isPaid status in the cell
            descCell.dataset.isPaid = isPaid ? '1' : '0';

            descCell.addEventListener('click', function() {
                const transId = parseInt(this.dataset.transactionId);
                const cellIsPaid = this.dataset.isPaid === '1';

                // If already paid, unpay it. Otherwise, show payment modal
                if (cellIsPaid) {
                    markTransactionAsUnpaid(transId);
                } else {
                    showPaymentMethodModal(transId, true); // true = isPaidClick
                }
            });
        }

        tbody.appendChild(row);
    });
}

function loadPaymentTotals() {
    // Parse month/year from the month picker (format: YYYY-MM)
    const monthYearPicker = document.getElementById('monthYearPicker');
    let year, month;

    if (monthYearPicker && monthYearPicker.value) {
        const [yearStr, monthStr] = monthYearPicker.value.split('-');
        year = parseInt(yearStr);
        month = parseInt(monthStr);
    } else {
        year = new Date().getFullYear();
        month = new Date().getMonth() + 1;
    }

    showLoading();

    fetch(`/api/payment-method-totals?year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => {
            displayPaymentTotals(data);
            hideLoading();
        })
        .catch(error => {
            console.error('Error loading payment totals:', error);
            showToast('Error loading payment totals', 'danger');
            hideLoading();
        });
}

function displayPaymentTotals(totals) {
    const container = document.getElementById('paymentTotalsContent');
    if (!container) return;

    container.innerHTML = '';

    if (!totals || totals.length === 0) {
        container.innerHTML = '<div class="alert alert-warning">No payment methods found with transactions.</div>';
        return;
    }

    let totalDebit = 0;
    let totalCredit = 0;

    const html = `
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>Payment Method</th>
                        <th>Type</th>
                        <th>Transactions</th>
                        <th class="text-end">Total Debit</th>
                        <th class="text-end">Total Credit</th>
                        <th class="text-end">Net Amount</th>
                    </tr>
                </thead>
                <tbody>
                    ${totals.map(t => {
                        const debit = t.total_debit || 0;
                        const credit = t.total_credit || 0;
                        const net = t.net_amount || 0;
                        totalDebit += debit;
                        totalCredit += credit;

                        return `
                            <tr>
                                <td>
                                    <span class="payment-method-color-indicator" style="background-color: ${t.color}"></span>
                                    <strong>${t.name}</strong>
                                </td>
                                <td>
                                    <span class="badge ${t.type === 'cash' ? 'bg-success' : 'bg-info'}">
                                        ${t.type === 'cash' ? 'Cash' : 'Credit Card'}
                                    </span>
                                </td>
                                <td>${t.transaction_count || 0}</td>
                                <td class="text-end text-success">${formatCurrency(debit)}</td>
                                <td class="text-end text-danger">${formatCurrency(credit)}</td>
                                <td class="text-end fw-bold ${net >= 0 ? 'text-success' : 'text-danger'}">
                                    ${formatCurrency(net)}
                                </td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
                <tfoot>
                    <tr class="table-active fw-bold">
                        <td colspan="3">TOTAL</td>
                        <td class="text-end text-success">${formatCurrency(totalDebit)}</td>
                        <td class="text-end text-danger">${formatCurrency(totalCredit)}</td>
                        <td class="text-end ${(totalDebit - totalCredit) >= 0 ? 'text-success' : 'text-danger'}">
                            ${formatCurrency(totalDebit - totalCredit)}
                        </td>
                    </tr>
                </tfoot>
            </table>
        </div>
    `;

    container.innerHTML = html;
}

function editTransaction(id) {
    // Find the transaction in the table by exact ID match
    const tbody = document.querySelector('#transactionsTable tbody');
    const rows = tbody.querySelectorAll('tr[data-transaction]');

    let transaction = null;
    for (const row of rows) {
        try {
            const data = JSON.parse(row.dataset.transaction);
            if (data.id === id) {
                transaction = data;
                break;
            }
        } catch (e) {
            continue;
        }
    }

    if (!transaction) {
        console.error('Transaction not found:', id);
        showToast('Transaction not found', 'danger');
        return;
    }

    // Populate form
    document.getElementById('editTransactionId').value = transaction.id;
    document.getElementById('transDescription').value = transaction.description || '';
    document.getElementById('transCategory').value = transaction.category_id || '';
    document.getElementById('transDebit').value = transaction.debit || '';
    document.getElementById('transCredit').value = transaction.credit || '';
    document.getElementById('transDate').value = transaction.transaction_date ? transaction.transaction_date.split('T')[0] : '';
    document.getElementById('transNotes').value = transaction.notes || '';

    // Update modal title
    document.querySelector('#transactionModal .modal-title').textContent = 'Edit Transaction';

    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('transactionModal'));
    modal.show();
}

function saveTransaction() {
    const editId = document.getElementById('editTransactionId')?.value;
    const isEdit = editId && editId !== '';

    // Parse month/year from the month picker (format: YYYY-MM)
    const monthYearPicker = document.getElementById('monthYearPicker');
    let year, month;

    if (monthYearPicker && monthYearPicker.value) {
        const [yearStr, monthStr] = monthYearPicker.value.split('-');
        year = parseInt(yearStr);
        month = parseInt(monthStr);
    } else {
        year = new Date().getFullYear();
        month = new Date().getMonth() + 1;
    }

    // Validate description
    const description = document.getElementById('transDescription')?.value;
    if (!description || description.trim() === '') {
        showToast('Description is required', 'danger');
        return;
    }

    // Get raw values
    const debitValue = document.getElementById('transDebit')?.value;
    const creditValue = document.getElementById('transCredit')?.value;

    // Parse and validate values - handle empty strings properly
    let debit = null;
    let credit = null;

    if (debitValue && debitValue.trim() !== '') {
        debit = parseFloat(debitValue);
        if (isNaN(debit) || debit < 0) {
            showToast('Debit must be a valid positive number', 'danger');
            return;
        }
    }

    if (creditValue && creditValue.trim() !== '') {
        credit = parseFloat(creditValue);
        if (isNaN(credit) || credit < 0) {
            showToast('Credit must be a valid positive number', 'danger');
            return;
        }
    }

    const data = {
        description: description,
        category_id: document.getElementById('transCategory')?.value || null,
        debit: debit,
        credit: credit,
        transaction_date: document.getElementById('transDate')?.value,
        notes: document.getElementById('transNotes')?.value,
        year: parseInt(year),
        month: parseInt(month)
    };

    console.log('Saving transaction with data:', data);
    console.log('Debit value:', debitValue, 'Parsed:', debit);
    console.log('Credit value:', creditValue, 'Parsed:', credit);

    const url = isEdit ? `/api/transactions/${editId}` : '/api/transactions';
    const method = isEdit ? 'PUT' : 'POST';

    showLoading();

    fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(response => {
        console.log('Response status:', response.status);
        console.log('Response ok:', response.ok);
        console.log('Response headers:', response.headers.get('content-type'));

        // Get response as text first
        return response.text().then(text => {
            console.log('Response text (first 500 chars):', text.substring(0, 500));

            // Try to parse as JSON
            try {
                const result = JSON.parse(text);
                return { status: response.status, ok: response.ok, result };
            } catch (e) {
                console.error('Failed to parse JSON:', e);
                console.error('Full response text:', text);
                return { status: response.status, ok: false, result: { error: 'Server returned non-JSON response' } };
            }
        });
    })
    .then(({ status, ok, result }) => {
        console.log('Parsed result:', result);
        hideLoading();
        if (!ok || result.error) {
            const errorMsg = result.error || `Server error (${status})`;
            console.error('Save failed:', errorMsg);
            showToast(errorMsg, 'danger');
        } else {
            showToast(isEdit ? 'Transaction updated successfully' : 'Transaction saved successfully', 'success');
            closeModal('transactionModal');
            document.getElementById('transactionForm')?.reset();
            document.getElementById('editTransactionId').value = '';
            document.querySelector('#transactionModal .modal-title').textContent = 'Add Transaction';

            // Reset date to today after form reset
            const transDate = document.getElementById('transDate');
            if (transDate) {
                transDate.value = new Date().toISOString().split('T')[0];
            }

            loadTransactions();
            loadDashboardStats();
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error saving transaction:', error);
        showToast('Error saving transaction: ' + error.message, 'danger');
    });
}

function deleteTransaction(id) {
    showConfirmModal(
        'Delete Transaction',
        'Are you sure you want to delete this transaction? This action cannot be undone.',
        function() {
            showLoading();
            fetch(`/api/transactions/${id}`, { method: 'DELETE' })
                .then(response => response.json())
                .then(result => {
                    hideLoading();
                    showToast('Transaction deleted successfully', 'success');
                    loadTransactions();
                    loadDashboardStats();
                })
                .catch(error => {
                    hideLoading();
                    console.error('Error deleting transaction:', error);
                    showToast('Error deleting transaction', 'danger');
                });
        },
        'Delete',
        'btn-danger'
    );
}

// ================================
// AUDIT LOG FUNCTIONS
// ================================

function showAuditModal(transactionId) {
    const modal = new bootstrap.Modal(document.getElementById('auditLogModal'));
    const auditLogContent = document.getElementById('auditLogContent');

    // Show loading state
    auditLogContent.innerHTML = `
        <div class="text-center">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-2">Loading audit logs...</p>
        </div>
    `;

    // Show the modal
    modal.show();

    // Fetch audit logs
    fetch(`/api/transactions/${transactionId}/audit-logs`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to fetch audit logs');
            }
            return response.json();
        })
        .then(auditLogs => {
            displayAuditLogs(auditLogs);
        })
        .catch(error => {
            console.error('Error fetching audit logs:', error);
            auditLogContent.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error loading audit logs. Please try again.
                </div>
            `;
        });
}

function displayAuditLogs(auditLogs) {
    const auditLogContent = document.getElementById('auditLogContent');

    if (!auditLogs || auditLogs.length === 0) {
        auditLogContent.innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-info-circle me-2"></i>
                No audit logs found for this transaction.
            </div>
        `;
        return;
    }

    // Group logs by action
    const createLogs = auditLogs.filter(log => log.action === 'CREATE');
    const updateLogs = auditLogs.filter(log => log.action === 'UPDATE');
    const deleteLogs = auditLogs.filter(log => log.action === 'DELETE');

    let html = '<div class="audit-log-timeline">';

    // Helper function to format date
    const formatAuditDate = (dateStr) => {
        const date = new Date(dateStr);
        return date.toLocaleString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    };

    // Helper function to format field name
    const formatFieldName = (fieldName) => {
        if (!fieldName) return '';
        return fieldName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    };

    // Helper function to get action badge
    const getActionBadge = (action) => {
        const badges = {
            'CREATE': '<span class="badge bg-success">Created</span>',
            'UPDATE': '<span class="badge bg-primary">Updated</span>',
            'DELETE': '<span class="badge bg-danger">Deleted</span>'
        };
        return badges[action] || `<span class="badge bg-secondary">${action}</span>`;
    };

    // Display DELETE logs first (if any)
    if (deleteLogs.length > 0) {
        deleteLogs.forEach(log => {
            html += `
                <div class="audit-log-entry mb-3 p-3 border rounded" style="background-color: rgba(248, 249, 250, 0.5);">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <div>
                            ${getActionBadge(log.action)}
                            <span class="ms-2 opacity-75 small">by ${log.username}</span>
                        </div>
                        <span class="opacity-75 small">${formatAuditDate(log.created_at)}</span>
                    </div>
                    <div class="opacity-75">Transaction was deleted</div>
                </div>
            `;
        });
    }

    // Display UPDATE logs
    if (updateLogs.length > 0) {
        html += '<div class="mb-3"><strong>Changes:</strong></div>';
        updateLogs.forEach(log => {
            html += `
                <div class="audit-log-entry mb-3 p-3 border rounded">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <div>
                            ${getActionBadge(log.action)}
                            <strong class="ms-2">${formatFieldName(log.field_name)}</strong>
                            <span class="ms-2 opacity-75 small">by ${log.username}</span>
                        </div>
                        <span class="opacity-75 small">${formatAuditDate(log.created_at)}</span>
                    </div>
                    <div class="ms-3">
                        <div class="row">
                            <div class="col-md-6">
                                <small class="opacity-75">Old Value:</small>
                                <div class="text-danger">${log.old_value || '<em>empty</em>'}</div>
                            </div>
                            <div class="col-md-6">
                                <small class="opacity-75">New Value:</small>
                                <div class="text-success">${log.new_value || '<em>empty</em>'}</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
    }

    // Display CREATE logs last (original creation)
    if (createLogs.length > 0) {
        createLogs.forEach(log => {
            html += `
                <div class="audit-log-entry mb-3 p-3 border rounded" style="background-color: rgba(248, 249, 250, 0.5);">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <div>
                            ${getActionBadge(log.action)}
                            <span class="ms-2 opacity-75 small">by ${log.username}</span>
                        </div>
                        <span class="opacity-75 small">${formatAuditDate(log.created_at)}</span>
                    </div>
                    <div class="opacity-75">Transaction was created</div>
                </div>
            `;
        });
    }

    html += '</div>';

    auditLogContent.innerHTML = html;
}

// ================================
// MOVE/COPY TRANSACTION FUNCTIONS
// ================================

function showMoveCopyModal(transactionId, action) {
    // Find the transaction data
    const tbody = document.querySelector('#transactionsTable tbody');
    const rows = tbody.querySelectorAll('tr[data-transaction]');

    let transaction = null;
    for (const row of rows) {
        try {
            const data = JSON.parse(row.dataset.transaction);
            if (data.id === transactionId) {
                transaction = data;
                break;
            }
        } catch (e) {
            continue;
        }
    }

    if (!transaction) {
        console.error('Transaction not found:', transactionId);
        showToast('Transaction not found', 'danger');
        return;
    }

    // Update modal content based on action
    const modal = document.getElementById('moveCopyTransactionModal');
    const titleEl = document.getElementById('moveCopyTitle');
    const infoTextEl = document.getElementById('moveCopyInfoText');
    const confirmBtn = document.getElementById('executeMoveCopyBtn');

    if (action === 'move') {
        titleEl.textContent = 'Move Transaction';
        infoTextEl.textContent = 'This will move the transaction to the selected month and remove it from the current month.';
        confirmBtn.innerHTML = '<i class="fas fa-arrow-right me-1"></i>Move Transaction';
        confirmBtn.className = 'btn btn-warning';
    } else {
        titleEl.textContent = 'Copy Transaction';
        infoTextEl.textContent = 'This will create a copy of the transaction in the selected month.';
        confirmBtn.innerHTML = '<i class="fas fa-copy me-1"></i>Copy Transaction';
        confirmBtn.className = 'btn btn-primary';
    }

    // Display transaction info
    const transInfoEl = document.getElementById('moveCopyTransactionInfo');
    const amount = transaction.debit
        ? `<span class="text-success">Income: ${formatCurrency(transaction.debit)}</span>`
        : `<span class="text-danger">Expense: ${formatCurrency(transaction.credit)}</span>`;

    transInfoEl.innerHTML = `
        <div><strong>${transaction.description}</strong></div>
        <div class="small opacity-75">Category: ${transaction.category_name || 'Uncategorized'}</div>
        <div class="small">${amount}</div>
    `;

    // Set hidden fields
    document.getElementById('moveCopyTransactionId').value = transactionId;
    document.getElementById('moveCopyAction').value = action;

    // Set default target month to current month
    const now = new Date();
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    document.getElementById('targetMonthYear').value = currentMonth;

    // Show modal
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

// Event listener for execute button
document.addEventListener('DOMContentLoaded', function() {
    const executeBtn = document.getElementById('executeMoveCopyBtn');
    if (executeBtn) {
        executeBtn.addEventListener('click', executeMoveCopyTransaction);
    }
});

function executeMoveCopyTransaction() {
    const transactionId = document.getElementById('moveCopyTransactionId').value;
    const action = document.getElementById('moveCopyAction').value;
    const targetMonthYear = document.getElementById('targetMonthYear').value;

    if (!targetMonthYear) {
        showToast('Please select a target month', 'warning');
        return;
    }

    // Parse target month/year
    const [targetYear, targetMonth] = targetMonthYear.split('-').map(Number);

    // Confirmation
    const actionText = action === 'move' ? 'move' : 'copy';
    const monthName = new Date(targetYear, targetMonth - 1).toLocaleString('default', { month: 'long', year: 'numeric' });

    showConfirmModal(
        `${action === 'move' ? 'Move' : 'Copy'} Transaction`,
        `Are you sure you want to ${actionText} this transaction to ${monthName}?`,
        function() {
            performMoveCopyTransaction(transactionId, action, targetYear, targetMonth);
        },
        action === 'move' ? 'Move' : 'Copy',
        action === 'move' ? 'btn-warning' : 'btn-primary'
    );
}

function performMoveCopyTransaction(transactionId, action, targetYear, targetMonth) {
    showLoading();

    const url = `/api/transactions/${transactionId}/${action}`;

    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            target_year: targetYear,
            target_month: targetMonth
        })
    })
    .then(response => response.json())
    .then(result => {
        hideLoading();

        if (result.error) {
            showToast(result.error, 'danger');
        } else {
            const actionText = action === 'move' ? 'moved' : 'copied';
            showToast(result.message || `Transaction ${actionText} successfully`, 'success');

            // Close the modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('moveCopyTransactionModal'));
            if (modal) modal.hide();

            // Reload transactions
            loadTransactions();
            loadDashboardStats();
        }
    })
    .catch(error => {
        hideLoading();
        console.error(`Error ${action}ing transaction:`, error);
        showToast(`Error ${action}ing transaction`, 'danger');
    });
}

// ================================
// TRANSACTION FILTERS
// ================================

// ================================
// FILTER FUNCTIONS - REVAMPED
// ================================

function populateFilterDropdowns() {
    // Only initialize once to prevent duplicate event listeners
    if (filterDropdownsInitialized) {
        return;
    }

    // Populate categories
    const categoryContainer = document.getElementById('filterCategoryCheckboxes');
    if (categoryContainer && currentCategories.length > 0) {
        categoryContainer.innerHTML = '';
        currentCategories.forEach(cat => {
            const iconClass = cat.type === 'income' ? 'fa-arrow-down text-success' : 'fa-arrow-up text-danger';
            const checkbox = document.createElement('div');
            checkbox.className = 'form-check';
            checkbox.innerHTML = `
                <input class="form-check-input filter-category-checkbox" type="checkbox" value="${cat.id}" id="filterCat${cat.id}">
                <label class="form-check-label" for="filterCat${cat.id}">
                    <i class="fas ${iconClass} me-1"></i>${cat.name}
                </label>
            `;
            categoryContainer.appendChild(checkbox);
        });
    }

    // Populate payment methods
    const paymentContainer = document.getElementById('filterPaymentMethodCheckboxes');
    if (paymentContainer && Array.isArray(paymentMethods) && paymentMethods.length > 0) {
        paymentContainer.innerHTML = '';
        paymentMethods.forEach(method => {
            const iconClass = method.type === 'cash' ? 'fa-money-bill-wave' : 'fa-credit-card';
            const checkbox = document.createElement('div');
            checkbox.className = 'form-check';
            checkbox.innerHTML = `
                <input class="form-check-input filter-payment-checkbox" type="checkbox" value="${method.id}" id="filterPay${method.id}">
                <label class="form-check-label" for="filterPay${method.id}">
                    <i class="fas ${iconClass} me-1"></i>${method.name}
                </label>
            `;
            paymentContainer.appendChild(checkbox);
        });
    }

    filterDropdownsInitialized = true;
}

// Quick Filter Functions
function applyQuickFilter(filterType) {
    // Clear all filters first
    clearFiltersWithoutReload();

    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    const todayStr = `${yyyy}-${mm}-${dd}`;

    switch(filterType) {
        case 'today':
            document.getElementById('filterStartDate').value = todayStr;
            document.getElementById('filterEndDate').value = todayStr;
            break;

        case 'last7days':
            const last7days = new Date(today);
            last7days.setDate(last7days.getDate() - 7);
            const yyyy7 = last7days.getFullYear();
            const mm7 = String(last7days.getMonth() + 1).padStart(2, '0');
            const dd7 = String(last7days.getDate()).padStart(2, '0');
            document.getElementById('filterStartDate').value = `${yyyy7}-${mm7}-${dd7}`;
            document.getElementById('filterEndDate').value = todayStr;
            break;

        case 'thisMonth':
            const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
            const yyyyFirst = firstDay.getFullYear();
            const mmFirst = String(firstDay.getMonth() + 1).padStart(2, '0');
            document.getElementById('filterStartDate').value = `${yyyyFirst}-${mmFirst}-01`;
            document.getElementById('filterEndDate').value = todayStr;
            break;

        case 'income':
            document.getElementById('filterTypeIncome').checked = true;
            break;

        case 'expense':
            document.getElementById('filterTypeExpense').checked = true;
            break;

        case 'unpaid':
            document.getElementById('filterStatusUnpaid').checked = true;
            break;
    }

    // Apply the filters
    applyFilters();
}

// Select/Deselect All Functions
function selectAllCategories() {
    document.querySelectorAll('.filter-category-checkbox').forEach(cb => cb.checked = true);
}

function deselectAllCategories() {
    document.querySelectorAll('.filter-category-checkbox').forEach(cb => cb.checked = false);
}

function selectAllPaymentMethods() {
    document.querySelectorAll('.filter-payment-checkbox').forEach(cb => cb.checked = true);
}

function deselectAllPaymentMethods() {
    document.querySelectorAll('.filter-payment-checkbox').forEach(cb => cb.checked = false);
}

function applyFilters() {
    // Get filter values
    activeFilters.description = document.getElementById('filterDescription')?.value.trim() || '';
    activeFilters.notes = document.getElementById('filterNotes')?.value.trim() || '';

    // Get selected categories (from checkboxes)
    activeFilters.categories = [];
    document.querySelectorAll('.filter-category-checkbox:checked').forEach(checkbox => {
        activeFilters.categories.push(checkbox.value);
    });

    // Get selected payment methods (from checkboxes)
    activeFilters.paymentMethods = [];
    document.querySelectorAll('.filter-payment-checkbox:checked').forEach(checkbox => {
        activeFilters.paymentMethods.push(checkbox.value);
    });

    // Get selected types (from checkboxes)
    activeFilters.types = [];
    document.querySelectorAll('.filter-type-checkbox:checked').forEach(checkbox => {
        activeFilters.types.push(checkbox.value);
    });

    // Get selected statuses (from checkboxes)
    activeFilters.statuses = [];
    document.querySelectorAll('.filter-status-checkbox:checked').forEach(checkbox => {
        activeFilters.statuses.push(checkbox.value);
    });

    // Get amount range
    const minAmount = document.getElementById('filterMinAmount')?.value;
    const maxAmount = document.getElementById('filterMaxAmount')?.value;
    activeFilters.minAmount = minAmount ? parseFloat(minAmount) : null;
    activeFilters.maxAmount = maxAmount ? parseFloat(maxAmount) : null;

    // Get date range
    activeFilters.startDate = document.getElementById('filterStartDate')?.value || null;
    activeFilters.endDate = document.getElementById('filterEndDate')?.value || null;

    console.log('Active filters:', activeFilters);

    // Update active filters display
    displayActiveFilters();

    // Close modal
    closeModal('filterModal');

    // Load transactions from backend with filters
    loadTransactions(true);

    showToast('Filters applied successfully', 'success');
}

function clearFiltersWithoutReload() {
    // Reset filter values
    activeFilters = {
        description: '',
        categories: [],
        paymentMethods: [],
        types: [],
        statuses: [],
        minAmount: null,
        maxAmount: null,
        startDate: null,
        endDate: null,
        notes: ''
    };

    // Clear form inputs
    const descInput = document.getElementById('filterDescription');
    const notesInput = document.getElementById('filterNotes');
    const minAmountInput = document.getElementById('filterMinAmount');
    const maxAmountInput = document.getElementById('filterMaxAmount');
    const startDateInput = document.getElementById('filterStartDate');
    const endDateInput = document.getElementById('filterEndDate');

    if (descInput) descInput.value = '';
    if (notesInput) notesInput.value = '';
    if (minAmountInput) minAmountInput.value = '';
    if (maxAmountInput) maxAmountInput.value = '';
    if (startDateInput) startDateInput.value = '';
    if (endDateInput) endDateInput.value = '';

    // Uncheck all filter checkboxes
    document.querySelectorAll('.filter-category-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });
    document.querySelectorAll('.filter-payment-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });
    document.querySelectorAll('.filter-type-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });
    document.querySelectorAll('.filter-status-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });

    // Update active filters display and badge
    displayActiveFilters();
}

function clearFilters() {
    clearFiltersWithoutReload();

    // Close the modal
    closeModal('filterModal');

    // Reload transactions from backend without filters
    loadTransactions(false);

    showToast('All filters cleared', 'info');
}

function displayActiveFilters() {
    const container = document.getElementById('activeFiltersDisplay');
    const listEl = document.getElementById('activeFiltersList');

    if (!container || !listEl) return;

    listEl.innerHTML = '';
    let hasActiveFilters = false;

    // Description filter
    if (activeFilters.description) {
        hasActiveFilters = true;
        listEl.innerHTML += `
            <span class="badge bg-primary rounded-pill">
                <i class="fas fa-file-alt me-1"></i>Description: "${activeFilters.description}"
            </span>`;
    }

    // Notes filter
    if (activeFilters.notes) {
        hasActiveFilters = true;
        listEl.innerHTML += `
            <span class="badge bg-primary rounded-pill">
                <i class="fas fa-sticky-note me-1"></i>Notes: "${activeFilters.notes}"
            </span>`;
    }

    // Category filter (multiple)
    if (activeFilters.categories.length > 0) {
        hasActiveFilters = true;
        const categoryNames = activeFilters.categories.map(catId => {
            const cat = currentCategories.find(c => c.id == catId);
            return cat ? cat.name : catId;
        }).join(', ');
        listEl.innerHTML += `
            <span class="badge bg-info text-dark rounded-pill">
                <i class="fas fa-tags me-1"></i>Categories: ${categoryNames}
            </span>`;
    }

    // Payment method filter (multiple)
    if (activeFilters.paymentMethods.length > 0) {
        hasActiveFilters = true;
        const methodNames = activeFilters.paymentMethods.map(methodId => {
            const method = paymentMethods.find(m => m.id == methodId);
            return method ? method.name : methodId;
        }).join(', ');
        listEl.innerHTML += `
            <span class="badge bg-info text-dark rounded-pill">
                <i class="fas fa-credit-card me-1"></i>Payment: ${methodNames}
            </span>`;
    }

    // Type filter (multiple)
    if (activeFilters.types.length > 0) {
        hasActiveFilters = true;
        const typeLabels = activeFilters.types.map(type =>
            type === 'income' ? '<i class="fas fa-arrow-down"></i> Income' : '<i class="fas fa-arrow-up"></i> Expense'
        ).join(', ');
        listEl.innerHTML += `
            <span class="badge bg-success rounded-pill">
                <i class="fas fa-exchange-alt me-1"></i>${typeLabels}
            </span>`;
    }

    // Status filter (multiple)
    if (activeFilters.statuses.length > 0) {
        hasActiveFilters = true;
        const statusLabels = activeFilters.statuses.map(status => {
            if (status === 'done') return '<i class="fas fa-check"></i> Done';
            if (status === 'not_done') return '<i class="fas fa-times"></i> Not Done';
            if (status === 'paid') return '<i class="fas fa-dollar-sign"></i> Paid';
            if (status === 'unpaid') return '<i class="fas fa-exclamation"></i> Unpaid';
            return status;
        }).join(', ');
        listEl.innerHTML += `
            <span class="badge bg-warning text-dark rounded-pill">
                ${statusLabels}
            </span>`;
    }

    // Amount range
    if (activeFilters.minAmount !== null || activeFilters.maxAmount !== null) {
        hasActiveFilters = true;
        let amountText = '';
        if (activeFilters.minAmount !== null && activeFilters.maxAmount !== null) {
            amountText = `${formatCurrency(activeFilters.minAmount)} - ${formatCurrency(activeFilters.maxAmount)}`;
        } else if (activeFilters.minAmount !== null) {
            amountText = `≥ ${formatCurrency(activeFilters.minAmount)}`;
        } else {
            amountText = `≤ ${formatCurrency(activeFilters.maxAmount)}`;
        }
        listEl.innerHTML += `
            <span class="badge bg-secondary rounded-pill">
                <i class="fas fa-dollar-sign me-1"></i>${amountText}
            </span>`;
    }

    // Date range
    if (activeFilters.startDate || activeFilters.endDate) {
        hasActiveFilters = true;
        let dateText = '';
        if (activeFilters.startDate && activeFilters.endDate) {
            dateText = `${activeFilters.startDate} to ${activeFilters.endDate}`;
        } else if (activeFilters.startDate) {
            dateText = `From ${activeFilters.startDate}`;
        } else {
            dateText = `Until ${activeFilters.endDate}`;
        }
        listEl.innerHTML += `
            <span class="badge bg-secondary rounded-pill">
                <i class="fas fa-calendar me-1"></i>${dateText}
            </span>`;
    }

    // Show/hide container
    container.style.display = hasActiveFilters ? 'block' : 'none';

    // Update filter button badge
    const filterBadge = document.getElementById('filterBadge');
    if (filterBadge) {
        if (hasActiveFilters) {
            // Count active filters
            let filterCount = 0;
            if (activeFilters.description) filterCount++;
            if (activeFilters.notes) filterCount++;
            if (activeFilters.categories.length > 0) filterCount++;
            if (activeFilters.paymentMethods.length > 0) filterCount++;
            if (activeFilters.types.length > 0) filterCount++;
            if (activeFilters.statuses.length > 0) filterCount++;
            if (activeFilters.minAmount !== null || activeFilters.maxAmount !== null) filterCount++;
            if (activeFilters.startDate || activeFilters.endDate) filterCount++;

            filterBadge.textContent = filterCount;
            filterBadge.style.display = 'inline-block';
        } else {
            filterBadge.style.display = 'none';
        }
    }

    // Show/hide page clear button
    const clearFiltersPageBtn = document.getElementById('clearFiltersPageBtn');
    if (clearFiltersPageBtn) {
        clearFiltersPageBtn.style.display = hasActiveFilters ? 'inline-block' : 'none';
    }
}

function executeCloneMonth() {
    // Parse month/year from the month pickers (format: YYYY-MM)
    const cloneFromMonthYear = document.getElementById('cloneFromMonthYear');
    const cloneToMonthYear = document.getElementById('cloneToMonthYear');
    const includePayments = document.getElementById('cloneWithPayments')?.checked || false;

    // Validation
    if (!cloneFromMonthYear?.value || !cloneToMonthYear?.value) {
        showToast('Please select all date fields', 'danger');
        return;
    }

    // Parse values
    const [fromYear, fromMonth] = cloneFromMonthYear.value.split('-').map(v => parseInt(v));
    const [toYear, toMonth] = cloneToMonthYear.value.split('-').map(v => parseInt(v));

    if (fromYear === toYear && fromMonth === toMonth) {
        showToast('Source and target months cannot be the same', 'danger');
        return;
    }

    // Create month names for confirmation
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                        'July', 'August', 'September', 'October', 'November', 'December'];
    const fromMonthName = monthNames[fromMonth - 1];
    const toMonthName = monthNames[toMonth - 1];

    showConfirmModal(
        'Clone Month Transactions',
        `Clone all transactions from ${fromMonthName} ${fromYear} to ${toMonthName} ${toYear}?`,
        function() {
            showLoading();

            fetch('/api/clone-month-transactions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    from_year: fromYear,
                    from_month: fromMonth,
                    to_year: toYear,
                    to_month: toMonth,
                    include_payments: includePayments
                })
            })
            .then(response => response.json())
            .then(data => {
                hideLoading();
                if (data.error) {
                    showToast(data.error, 'danger');
                } else {
                    showToast(data.message, 'success');
                    closeModal('cloneMonthModal');

                    // Reload transactions if viewing the target month
                    const monthYearPicker = document.getElementById('monthYearPicker');
                    if (monthYearPicker?.value) {
                        const [currentYear, currentMonth] = monthYearPicker.value.split('-').map(v => parseInt(v));
                        if (currentMonth === toMonth && currentYear === toYear) {
                            loadTransactions();
                        }
                    }
                }
            })
            .catch(error => {
                hideLoading();
                console.error('Error cloning transactions:', error);
                showToast('Error cloning transactions', 'danger');
            });
        },
        'Clone',
        'btn-primary'
    );
}

// ================================
// REPORTS PAGE
// ================================

function loadReports() {
    const year = new Date().getFullYear();
    const month = new Date().getMonth() + 1;

    // Initialize year and month selectors
    initializeReportFilters(year, month);

    // Initialize tab event listeners
    initializeReportTabListeners();

    // Load only the first active tab (Monthly Summary)
    loadReportTab('monthlyReport', year, month, 'monthly');
}

function initializeReportFilters(year, month) {
    const yearSelect = document.getElementById('reportYear');
    const monthSelect = document.getElementById('reportMonth');
    const rangeSelect = document.getElementById('reportRangeType');

    // Populate years (from 2020 to current year + 1)
    yearSelect.innerHTML = '';
    for (let y = year + 1; y >= 2020; y--) {
        const option = document.createElement('option');
        option.value = y;
        option.textContent = y;
        if (y === year) option.selected = true;
        yearSelect.appendChild(option);
    }

    // Set current month
    monthSelect.value = month;

    // Add event listeners only once
    if (!reportFiltersInitialized) {
        yearSelect.addEventListener('change', () => {
            const selectedYear = yearSelect.value;
            const selectedMonth = monthSelect.value;
            const selectedRange = rangeSelect.value;
            reloadActiveReportTab(selectedYear, selectedMonth, selectedRange);
        });

        monthSelect.addEventListener('change', () => {
            const selectedYear = yearSelect.value;
            const selectedMonth = monthSelect.value;
            const selectedRange = rangeSelect.value;
            reloadActiveReportTab(selectedYear, selectedMonth, selectedRange);
        });

        rangeSelect.addEventListener('change', () => {
            const selectedYear = yearSelect.value;
            const selectedMonth = monthSelect.value;
            const selectedRange = rangeSelect.value;

            // Show/hide month selector based on range type
            const monthContainer = document.getElementById('reportMonthContainer');
            if (selectedRange === 'yearly') {
                monthContainer.style.display = 'none';
            } else {
                monthContainer.style.display = 'block';
            }

            reloadActiveReportTab(selectedYear, selectedMonth, selectedRange);
        });

        reportFiltersInitialized = true;
    }
}

// Initialize tab event listeners for lazy loading
function initializeReportTabListeners() {
    if (reportTabsInitialized) return;

    const reportTabs = document.querySelectorAll('#reportTabs a[data-bs-toggle="tab"]');
    reportTabs.forEach(tab => {
        tab.addEventListener('shown.bs.tab', (event) => {
            const targetId = event.target.getAttribute('href').substring(1); // Remove '#' from href
            const yearSelect = document.getElementById('reportYear');
            const monthSelect = document.getElementById('reportMonth');
            const rangeSelect = document.getElementById('reportRangeType');

            const year = yearSelect.value;
            const month = monthSelect.value;
            const rangeType = rangeSelect.value;

            loadReportTab(targetId, year, month, rangeType);
        });
    });

    reportTabsInitialized = true;
}

// Load a specific report tab's data
function loadReportTab(tabId, year, month, rangeType) {
    // Check if this tab has already been loaded
    if (loadedReportTabs.has(tabId)) {
        return; // Already loaded, no need to fetch again
    }

    showLoading();

    let fetchPromise;
    switch (tabId) {
        case 'monthlyReport':
            fetchPromise = loadMonthlyReport(year);
            break;
        case 'categoryReport':
            fetchPromise = loadCategoryReport(year, month, rangeType);
            break;
        case 'cashFlowReport':
            fetchPromise = loadCashFlowReport(year, month, rangeType);
            break;
        case 'topSpendingReport':
            fetchPromise = loadTopSpendingReport(year, month, rangeType);
            break;
        case 'forecastReport':
            fetchPromise = loadForecastReport();
            break;
        default:
            hideLoading();
            return;
    }

    fetchPromise
        .then(() => {
            loadedReportTabs.add(tabId); // Mark this tab as loaded
            hideLoading();
        })
        .catch(error => {
            hideLoading();
            console.error(`Error loading ${tabId}:`, error);
            showToast('Error loading report', 'danger');
        });
}

// Reload the currently active report tab (when filters change)
function reloadActiveReportTab(year, month, rangeType) {
    const activeTab = document.querySelector('#reportTabs a.nav-link.active');
    if (!activeTab) return;

    const targetId = activeTab.getAttribute('href').substring(1);

    // Remove from loaded set to force reload
    loadedReportTabs.delete(targetId);

    // Reload the tab
    loadReportTab(targetId, year, month, rangeType);
}

// Individual report loading functions
function loadMonthlyReport(year) {
    return fetch(`/api/reports/monthly-summary?year=${year}`)
        .then(response => response.json())
        .then(data => updateMonthlyReportChart(data));
}

function loadCategoryReport(year, month, rangeType) {
    return fetch(`/api/reports/category-breakdown?range=${rangeType}&year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => updateCategoryReportChart(data, rangeType));
}

function loadCashFlowReport(year, month, rangeType) {
    return fetch(`/api/reports/cash-flow?range=${rangeType}&year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => updateCashFlowChart(data, rangeType));
}

function loadTopSpendingReport(year, month, rangeType) {
    return fetch(`/api/reports/top-spending?range=${rangeType}&year=${year}&month=${month}&limit=10`)
        .then(response => response.json())
        .then(data => updateTopSpendingChart(data));
}

function loadForecastReport() {
    return fetch(`/api/reports/forecast?months=6`)
        .then(response => response.json())
        .then(data => updateForecastChart(data));
}

// ================================
// CHARTS
// ================================

function initCharts() {
    // Trend Chart
    const trendCtx = document.getElementById('trendChart');
    if (trendCtx) {
        charts.trend = new Chart(trendCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Income',
                    data: [],
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    tension: 0.1
                }, {
                    label: 'Expenses',
                    data: [],
                    borderColor: 'rgb(255, 99, 132)',
                    backgroundColor: 'rgba(255, 99, 132, 0.2)',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: value => 'LKR ' + value.toLocaleString()
                        }
                    }
                }
            }
        });
    }

    // Category Chart
    const categoryCtx = document.getElementById('categoryChart');
    if (categoryCtx) {
        charts.category = new Chart(categoryCtx, {
            type: 'doughnut',
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    backgroundColor: [
                        'rgba(255, 99, 132, 0.8)',
                        'rgba(54, 162, 235, 0.8)',
                        'rgba(255, 206, 86, 0.8)',
                        'rgba(75, 192, 192, 0.8)',
                        'rgba(153, 102, 255, 0.8)',
                        'rgba(255, 159, 64, 0.8)'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom' }
                }
            }
        });
    }
}

function updateTrendChart(data) {
    if (!charts.trend || !data) return;

    const labels = [];
    const income = [];
    const expenses = [];

    data.slice().reverse().forEach(item => {
        labels.push(`${item.month_name} ${item.year}`);
        income.push(item.income || 0);
        expenses.push(item.expenses || 0);
    });

    charts.trend.data.labels = labels;
    charts.trend.data.datasets[0].data = income;
    charts.trend.data.datasets[1].data = expenses;
    charts.trend.update();
}

function updateMonthlyReportChart(data) {
    const ctx = document.getElementById('monthlyReportChart');
    if (!ctx || !data) return;

    if (charts.monthlyReport) {
        charts.monthlyReport.destroy();
    }

    const labels = data.map(d => `${d.month_name} ${d.year}`);
    const income = data.map(d => d.total_income || 0);
    const expenses = data.map(d => d.total_expenses || 0);
    const savings = data.map(d => d.net_savings || 0);

    charts.monthlyReport = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Income',
                data: income,
                backgroundColor: 'rgba(75, 192, 192, 0.8)'
            }, {
                label: 'Expenses',
                data: expenses,
                backgroundColor: 'rgba(255, 99, 132, 0.8)'
            }, {
                label: 'Net Savings',
                data: savings,
                backgroundColor: 'rgba(54, 162, 235, 0.8)'
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: value => 'LKR ' + value.toLocaleString()
                    }
                }
            }
        }
    });
}

function updateCategoryReportChart(data, rangeType) {
    if (!data) return;

    // Destroy old charts if they exist
    if (charts.categoryIncome) {
        charts.categoryIncome.destroy();
    }
    if (charts.categoryExpense) {
        charts.categoryExpense.destroy();
    }

    // Aggregate data by category across all time periods
    const categoryTotals = {};
    data.forEach(item => {
        if (!categoryTotals[item.category]) {
            categoryTotals[item.category] = {
                type: item.type,
                income: 0,
                expense: 0
            };
        }
        categoryTotals[item.category].income += parseFloat(item.income || 0);
        categoryTotals[item.category].expense += parseFloat(item.expense || 0);
    });

    // Separate income and expense categories
    const incomeCategories = [];
    const incomeAmounts = [];
    const expenseCategories = [];
    const expenseAmounts = [];
    let totalIncome = 0;
    let totalExpense = 0;

    Object.entries(categoryTotals).forEach(([category, data]) => {
        if (data.type === 'income' && data.income > 0) {
            incomeCategories.push(category);
            incomeAmounts.push(data.income);
            totalIncome += data.income;
        } else if (data.type === 'expense' && data.expense > 0) {
            expenseCategories.push(category);
            expenseAmounts.push(data.expense);
            totalExpense += data.expense;
        }
    });

    // Create Income Chart (Horizontal Bar Chart)
    const incomeCtx = document.getElementById('categoryIncomeChart');
    if (incomeCtx && incomeCategories.length > 0) {
        charts.categoryIncome = new Chart(incomeCtx, {
            type: 'doughnut',
            data: {
                labels: incomeCategories,
                datasets: [{
                    data: incomeAmounts,
                    backgroundColor: [
                        'rgba(75, 192, 192, 0.8)',
                        'rgba(54, 162, 235, 0.8)',
                        'rgba(153, 102, 255, 0.8)',
                        'rgba(144, 238, 144, 0.8)',
                        'rgba(135, 206, 250, 0.8)',
                        'rgba(176, 224, 230, 0.8)'
                    ],
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: ctx => {
                                const percentage = ((ctx.parsed / totalIncome) * 100).toFixed(1);
                                return ctx.label + ': LKR ' + ctx.parsed.toLocaleString() + ' (' + percentage + '%)';
                            }
                        }
                    }
                }
            }
        });
    }

    // Create Expense Chart (Horizontal Bar Chart)
    const expenseCtx = document.getElementById('categoryExpenseChart');
    if (expenseCtx && expenseCategories.length > 0) {
        charts.categoryExpense = new Chart(expenseCtx, {
            type: 'doughnut',
            data: {
                labels: expenseCategories,
                datasets: [{
                    data: expenseAmounts,
                    backgroundColor: [
                        'rgba(255, 99, 132, 0.8)',
                        'rgba(255, 159, 64, 0.8)',
                        'rgba(255, 206, 86, 0.8)',
                        'rgba(255, 99, 71, 0.8)',
                        'rgba(201, 203, 207, 0.8)',
                        'rgba(240, 230, 140, 0.8)',
                        'rgba(189, 183, 107, 0.8)',
                        'rgba(255, 182, 193, 0.8)',
                        'rgba(221, 160, 221, 0.8)',
                        'rgba(255, 228, 181, 0.8)'
                    ],
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: ctx => {
                                const percentage = ((ctx.parsed / totalExpense) * 100).toFixed(1);
                                return ctx.label + ': LKR ' + ctx.parsed.toLocaleString() + ' (' + percentage + '%)';
                            }
                        }
                    }
                }
            }
        });
    }

    // Update summary tables
    updateCategorySummaryTables(categoryTotals, totalIncome, totalExpense);

    // Update net savings
    updateNetSavings(totalIncome, totalExpense);
}

// Helper function to get consistent colors for categories
function getColorForIndex(index) {
    const colors = [
        'rgba(255, 99, 132, 0.8)',
        'rgba(54, 162, 235, 0.8)',
        'rgba(255, 206, 86, 0.8)',
        'rgba(75, 192, 192, 0.8)',
        'rgba(153, 102, 255, 0.8)',
        'rgba(255, 159, 64, 0.8)',
        'rgba(201, 203, 207, 0.8)',
        'rgba(255, 99, 71, 0.8)',
        'rgba(144, 238, 144, 0.8)',
        'rgba(135, 206, 250, 0.8)',
        'rgba(255, 182, 193, 0.8)',
        'rgba(176, 224, 230, 0.8)',
        'rgba(221, 160, 221, 0.8)',
        'rgba(240, 230, 140, 0.8)',
        'rgba(189, 183, 107, 0.8)'
    ];
    return colors[index % colors.length];
}

// Update category summary tables (separate income and expense)
function updateCategorySummaryTables(categoryTotals, totalIncome, totalExpense) {
    const incomeTableBody = document.getElementById('incomeTableBody');
    const expenseTableBody = document.getElementById('expenseTableBody');
    const totalIncomeElement = document.getElementById('totalIncome');
    const totalExpensesElement = document.getElementById('totalExpenses');

    if (!incomeTableBody || !expenseTableBody) return;

    // Prepare income rows
    const incomeRows = [];
    const expenseRows = [];

    Object.entries(categoryTotals).forEach(([category, data]) => {
        if (data.type === 'income' && data.income > 0) {
            incomeRows.push({ category, amount: data.income });
        } else if (data.type === 'expense' && data.expense > 0) {
            expenseRows.push({ category, amount: data.expense });
        }
    });

    // Sort by amount descending
    incomeRows.sort((a, b) => b.amount - a.amount);
    expenseRows.sort((a, b) => b.amount - a.amount);

    // Build income table HTML
    incomeTableBody.innerHTML = incomeRows.map(row => {
        const percentage = totalIncome > 0 ? ((row.amount / totalIncome) * 100).toFixed(1) : 0;
        return `
            <tr>
                <td>${row.category}</td>
                <td class="text-end">LKR ${row.amount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                <td class="text-end">${percentage}%</td>
            </tr>
        `;
    }).join('');

    // Build expense table HTML
    expenseTableBody.innerHTML = expenseRows.map(row => {
        const percentage = totalExpense > 0 ? ((row.amount / totalExpense) * 100).toFixed(1) : 0;
        return `
            <tr>
                <td>${row.category}</td>
                <td class="text-end">LKR ${row.amount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                <td class="text-end">${percentage}%</td>
            </tr>
        `;
    }).join('');

    // Update totals
    totalIncomeElement.textContent = `LKR ${totalIncome.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    totalExpensesElement.textContent = `LKR ${totalExpense.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
}

// Update net savings display
function updateNetSavings(totalIncome, totalExpense) {
    const netSavingsElement = document.getElementById('netSavings');
    const savingsPercentageElement = document.getElementById('savingsPercentage');
    const netSavingsCard = document.getElementById('netSavingsCard');

    if (!netSavingsElement || !savingsPercentageElement || !netSavingsCard) return;

    const netSavings = totalIncome - totalExpense;
    const savingsRate = totalIncome > 0 ? ((netSavings / totalIncome) * 100).toFixed(1) : 0;

    // Update text
    netSavingsElement.textContent = `LKR ${netSavings.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    savingsPercentageElement.textContent = `${savingsRate}% savings rate`;

    // Update card styling based on savings
    netSavingsCard.className = 'card';
    if (netSavings > 0) {
        netSavingsCard.classList.add('border-success');
        netSavingsElement.classList.add('text-success');
    } else if (netSavings < 0) {
        netSavingsCard.classList.add('border-danger');
        netSavingsElement.classList.add('text-danger');
    } else {
        netSavingsCard.classList.add('border-secondary');
        netSavingsElement.classList.add('text-secondary');
    }
}

function updateCashFlowChart(data, rangeType) {
    const ctx = document.getElementById('cashFlowReportChart');
    if (!ctx || !data) return;

    if (charts.cashFlowReport) {
        charts.cashFlowReport.destroy();
    }

    let labels, cashIn, cashOut, netFlow;

    if (rangeType === 'weekly') {
        labels = data.map(d => `Week ${d.week_num}: ${d.week_start} to ${d.week_end}`);
        cashIn = data.map(d => d.cash_in || 0);
        cashOut = data.map(d => d.cash_out || 0);
        netFlow = data.map(d => d.net_flow || 0);
    } else if (rangeType === 'yearly') {
        labels = data.map(d => `${d.year}`);
        cashIn = data.map(d => d.cash_in || 0);
        cashOut = data.map(d => d.cash_out || 0);
        netFlow = data.map(d => d.net_flow || 0);
    } else {
        labels = data.map(d => `${d.month_name} ${d.year}`);
        cashIn = data.map(d => d.cash_in || 0);
        cashOut = data.map(d => d.cash_out || 0);
        netFlow = data.map(d => d.net_flow || 0);
    }

    charts.cashFlowReport = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Cash In',
                data: cashIn,
                borderColor: 'rgba(75, 192, 192, 1)',
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                fill: true,
                tension: 0.4
            }, {
                label: 'Cash Out',
                data: cashOut,
                borderColor: 'rgba(255, 99, 132, 1)',
                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                fill: true,
                tension: 0.4
            }, {
                label: 'Net Flow',
                data: netFlow,
                borderColor: 'rgba(54, 162, 235, 1)',
                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: value => 'LKR ' + value.toLocaleString()
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.dataset.label + ': LKR ' + ctx.parsed.y.toLocaleString()
                    }
                }
            }
        }
    });
}

function updateTopSpendingChart(data) {
    const ctx = document.getElementById('topSpendingReportChart');
    if (!ctx || !data) return;

    if (charts.topSpendingReport) {
        charts.topSpendingReport.destroy();
    }

    const labels = data.map(d => d.category || 'Uncategorized');
    const amounts = data.map(d => d.total_spent || 0);
    const counts = data.map(d => d.transaction_count || 0);

    charts.topSpendingReport = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Total Spent',
                data: amounts,
                backgroundColor: 'rgba(255, 99, 132, 0.8)',
                borderColor: 'rgba(255, 99, 132, 1)',
                borderWidth: 1
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    beginAtZero: true,
                    ticks: {
                        callback: value => 'LKR ' + value.toLocaleString()
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const index = ctx.dataIndex;
                            return [
                                'Total: LKR ' + ctx.parsed.x.toLocaleString(),
                                'Transactions: ' + counts[index],
                                'Average: LKR ' + (amounts[index] / counts[index]).toLocaleString()
                            ];
                        }
                    }
                }
            }
        }
    });
}

function updateForecastChart(data) {
    const ctx = document.getElementById('forecastReportChart');
    if (!ctx || !data) return;

    if (charts.forecastReport) {
        charts.forecastReport.destroy();
    }

    const forecast = data.next_month_forecast;
    const historical = data.historical_average;

    // Update forecast summary
    const summaryDiv = document.getElementById('forecastSummary');
    if (summaryDiv) {
        const confidenceText = forecast.confidence === 'medium' ? 'Medium' :
                               forecast.confidence === 'low' ? 'Low' : 'No Data';
        const trendText = forecast.expense_trend > 0 ?
            `trending up by ${forecast.expense_trend.toFixed(1)}%` :
            forecast.expense_trend < 0 ?
            `trending down by ${Math.abs(forecast.expense_trend).toFixed(1)}%` :
            'stable';

        summaryDiv.innerHTML = `
            <h5>Next Month Forecast (Confidence: ${confidenceText})</h5>
            <p><strong>Predicted Income:</strong> LKR ${forecast.predicted_income.toLocaleString()}</p>
            <p><strong>Predicted Expenses:</strong> LKR ${forecast.predicted_expenses.toLocaleString()}
               <span class="badge ${forecast.expense_trend > 0 ? 'bg-danger' : 'bg-success'}">${trendText}</span>
            </p>
            <p><strong>Predicted Savings:</strong> LKR ${forecast.predicted_savings.toLocaleString()}</p>
            <p class="opacity-75">Based on ${data.based_on_months} months of historical data</p>
        `;
    }

    // Create comparison chart
    charts.forecastReport = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Historical Average', 'Next Month Forecast'],
            datasets: [{
                label: 'Income',
                data: [historical.avg_income, forecast.predicted_income],
                backgroundColor: 'rgba(75, 192, 192, 0.8)'
            }, {
                label: 'Expenses',
                data: [historical.avg_expenses, forecast.predicted_expenses],
                backgroundColor: 'rgba(255, 99, 132, 0.8)'
            }, {
                label: 'Savings',
                data: [historical.avg_savings, forecast.predicted_savings],
                backgroundColor: 'rgba(54, 162, 235, 0.8)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: value => 'LKR ' + value.toLocaleString()
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.dataset.label + ': LKR ' + ctx.parsed.y.toLocaleString()
                    }
                }
            }
        }
    });

    // Update category forecast table
    const tbody = document.getElementById('forecastTableBody');
    if (tbody && data.category_forecast) {
        tbody.innerHTML = data.category_forecast.map(d => `
            <tr>
                <td>${d.category || 'Uncategorized'}</td>
                <td>LKR ${(d.avg_monthly_spending || 0).toLocaleString()}</td>
                <td>LKR ${(d.min_spending || 0).toLocaleString()}</td>
                <td>LKR ${(d.max_spending || 0).toLocaleString()}</td>
                <td>LKR ${(d.std_deviation || 0).toLocaleString()}</td>
            </tr>
        `).join('');
    }
}

// ================================
// UTILITIES
// ================================

function populateDateSelectors() {
    const currentYear = new Date().getFullYear();
    const currentMonth = new Date().getMonth() + 1;

    // Format current date as YYYY-MM for the month picker
    const currentMonthYear = `${currentYear}-${String(currentMonth).padStart(2, '0')}`;

    // Set min and max range (same as old dropdown: 2 years back to 1 year forward)
    const minYear = currentYear - 2;
    const maxYear = currentYear + 1;
    const minDate = `${minYear}-01`;
    const maxDate = `${maxYear}-12`;

    // Set main month/year picker
    const monthYearPicker = document.getElementById('monthYearPicker');
    if (monthYearPicker) {
        monthYearPicker.value = currentMonthYear;
        monthYearPicker.min = minDate;
        monthYearPicker.max = maxDate;
    }

    // Set clone modal month/year pickers
    const cloneFromMonthYear = document.getElementById('cloneFromMonthYear');
    if (cloneFromMonthYear) {
        cloneFromMonthYear.value = currentMonthYear;
        cloneFromMonthYear.min = minDate;
        cloneFromMonthYear.max = maxDate;
    }

    const cloneToMonthYear = document.getElementById('cloneToMonthYear');
    if (cloneToMonthYear) {
        cloneToMonthYear.value = currentMonthYear;
        cloneToMonthYear.min = minDate;
        cloneToMonthYear.max = maxDate;
    }

    // Add event listener for clone execute button
    const executeCloneBtn = document.getElementById('executeCloneBtn');
    if (executeCloneBtn) {
        executeCloneBtn.addEventListener('click', executeCloneMonth);
    }
}

function closeModal(modalId) {
    const modalEl = document.getElementById(modalId);
    if (modalEl) {
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) {
            modal.hide();
        }
    }
}

// ================================
// PAYMENT METHODS
// ================================

function loadPaymentMethods() {
    fetch('/api/payment-methods')
        .then(response => response.json())
        .then(methods => {
            // Ensure we always have an array
            paymentMethods = Array.isArray(methods) ? methods : [];
            console.log('✓ Loaded', paymentMethods.length, 'payment methods');

            // Populate filter dropdown
            const filterDropdown = document.getElementById('filterPaymentMethod');
            if (filterDropdown) {
                filterDropdown.innerHTML = '<option value="">All Payment Methods</option>';
                paymentMethods.forEach(method => {
                    filterDropdown.innerHTML += `<option value="${method.id}">${method.name}</option>`;
                });
            }
        })
        .catch(error => {
            console.error('✗ Error loading payment methods:', error);
            paymentMethods = []; // Ensure it stays an array on error
            showToast('Error loading payment methods', 'danger');
        });
}

function showPaymentMethodModal(transactionId, isPaidClick = false) {
    currentTransactionId = transactionId;
    const modalEl = document.getElementById('paymentMethodModal');
    const listEl = document.getElementById('paymentMethodList');

    // Clear and populate payment methods
    listEl.innerHTML = '';

    // Check if paymentMethods is an array
    if (!Array.isArray(paymentMethods) || paymentMethods.length === 0) {
        listEl.innerHTML = '<div class="alert alert-warning">No payment methods available. Please add a payment method first.</div>';
        const modal = new bootstrap.Modal(modalEl);
        modal.show();
        return;
    }

    paymentMethods.forEach(method => {
        const item = document.createElement('a');
        item.href = '#';
        item.className = 'list-group-item list-group-item-action payment-method-list-item';
        item.innerHTML = `
            <span class="payment-method-color-indicator" style="background-color: ${method.color}"></span>
            <strong>${method.name}</strong>
            <span class="badge bg-secondary float-end">${method.type === 'cash' ? 'Cash' : 'Credit Card'}</span>
        `;
        item.onclick = (e) => {
            e.preventDefault();
            if (isPaidClick) {
                markTransactionAsPaid(transactionId, method.id);
            } else {
                markTransactionWithPaymentMethod(transactionId, method.id);
            }
        };
        listEl.appendChild(item);
    });

    const modal = new bootstrap.Modal(modalEl);
    modal.show();
}

function markTransactionWithPaymentMethod(transactionId, paymentMethodId) {
    showLoading();

    // Get geolocation if available
    getGeolocation().then(location => {
        const requestBody = { payment_method_id: paymentMethodId };

        // Add location data if available
        if (location) {
            requestBody.latitude = location.latitude;
            requestBody.longitude = location.longitude;
            requestBody.accuracy = location.accuracy;
        }

        fetch(`/api/transactions/${transactionId}/mark-done`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        })
        .then(response => response.json())
        .then(data => {
            hideLoading();
            if (data.error) {
                showToast(data.error, 'danger');
            } else {
                showToast('Transaction marked as done', 'success');
                closeModal('paymentMethodModal');
                loadTransactions();
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Error:', error);
            showToast('Error marking transaction', 'danger');
        });
    });
}

function unmarkTransaction(transactionId) {
    showLoading();

    fetch(`/api/transactions/${transactionId}/mark-undone`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        showToast('Transaction unmarked', 'success');
        loadTransactions();
    })
    .catch(error => {
        hideLoading();
        console.error('Error:', error);
        showToast('Error unmarking transaction', 'danger');
    });
}

function markTransactionAsPaid(transactionId, paymentMethodId) {
    showLoading();

    // Get geolocation if available
    getGeolocation().then(location => {
        const requestBody = { payment_method_id: paymentMethodId };

        // Add location data if available
        if (location) {
            requestBody.latitude = location.latitude;
            requestBody.longitude = location.longitude;
            requestBody.accuracy = location.accuracy;
        }

        fetch(`/api/transactions/${transactionId}/mark-paid`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        })
        .then(response => response.json())
        .then(data => {
            hideLoading();
            if (data.error) {
                showToast(data.error, 'danger');
            } else {
                showToast('Transaction marked as paid', 'success');
                closeModal('paymentMethodModal');
                loadTransactions();
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Error:', error);
            showToast('Error marking transaction as paid', 'danger');
        });
    });
}

function markTransactionAsUnpaid(transactionId) {
    showLoading();

    fetch(`/api/transactions/${transactionId}/mark-unpaid`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.error) {
            showToast(data.error, 'danger');
        } else {
            showToast('Transaction marked as unpaid', 'success');
            loadTransactions();
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error:', error);
        showToast('Error unmarking transaction as paid', 'danger');
    });
}

function showAddCreditCardForm() {
    document.getElementById('addCreditCardForm').style.display = 'block';
}

function hideAddCreditCardForm() {
    document.getElementById('addCreditCardForm').style.display = 'none';
    document.getElementById('creditCardForm').reset();
}

function saveCreditCard(e) {
    e.preventDefault();

    const cardData = {
        name: document.getElementById('cardName').value,
        type: 'credit_card',
        color: document.getElementById('cardColor').value
    };

    showLoading();

    fetch('/api/payment-methods', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cardData)
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.error) {
            showToast(data.error, 'danger');
        } else {
            showToast('Credit card added successfully', 'success');
            hideAddCreditCardForm();
            loadPaymentMethods();
            loadCreditCardsList();
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error:', error);
        showToast('Error adding credit card', 'danger');
    });
}

function loadCreditCardsList() {
    const listEl = document.getElementById('creditCardsList');
    listEl.innerHTML = '';

    // Check if paymentMethods is an array
    if (!Array.isArray(paymentMethods)) {
        listEl.innerHTML = '<p class="opacity-75">No credit cards added yet.</p>';
        return;
    }

    const creditCards = paymentMethods.filter(m => m.type === 'credit_card');

    if (creditCards.length === 0) {
        listEl.innerHTML = '<p class="opacity-75">No credit cards added yet.</p>';
        return;
    }

    creditCards.forEach(card => {
        const item = document.createElement('div');
        item.className = 'credit-card-item';
        item.innerHTML = `
            <div class="credit-card-color" style="background-color: ${card.color}"></div>
            <div class="flex-grow-1">
                <strong>${card.name}</strong>
            </div>
            <button class="btn btn-sm btn-danger" onclick="deleteCreditCard(${card.id})">
                <i class="fas fa-trash"></i>
            </button>
        `;
        listEl.appendChild(item);
    });
}

function deleteCreditCard(cardId) {
    showConfirmModal(
        'Delete Credit Card',
        'Are you sure you want to delete this credit card? This action cannot be undone.',
        function() {
            showLoading();
            fetch(`/api/payment-methods/${cardId}`, {
                method: 'DELETE'
            })
            .then(response => response.json())
            .then(data => {
                hideLoading();
                showToast('Credit card deleted successfully', 'success');
                loadPaymentMethods();
                loadCreditCardsList();
            })
            .catch(error => {
                hideLoading();
                console.error('Error:', error);
                showToast('Error deleting credit card', 'danger');
            });
        },
        'Delete',
        'btn-danger'
    );
}

// Load credit cards when the manage modal is shown
document.addEventListener('DOMContentLoaded', function() {
    const manageCCModal = document.getElementById('manageCreditCardsModal');
    if (manageCCModal) {
        manageCCModal.addEventListener('shown.bs.modal', loadCreditCardsList);
    }
});

// ================================
// TAX CALCULATOR - Monthly Withholding Tax (Sri Lanka)
// ================================

// Month names for display
const monthNames = ['April', 'May', 'June', 'July', 'August', 'September',
                   'October', 'November', 'December', 'January', 'February', 'March'];

// Store last calculation data for saving
let lastCalculationData = null;

// Store all saved calculations for filtering
let allSavedCalculations = [];

function loadTaxCalculator() {
    console.log('Loading Tax Calculator...');

    // Setup event listeners
    const calculateBtn = document.getElementById('calculateTaxBtn');
    const resetBtn = document.getElementById('resetTaxBtn');
    const assessmentYearSelect = document.getElementById('assessmentYear');
    const startMonthSelect = document.getElementById('startMonth');
    const saveCalculationBtnAlt = document.getElementById('saveCalculationBtnAlt');
    const refreshSavedBtn = document.getElementById('refreshSavedCalculationsBtn');
    const loadSavedByYearBtn = document.getElementById('loadSavedByYearBtn');

    if (calculateBtn) {
        calculateBtn.onclick = calculateMonthlyTax;
    }

    if (resetBtn) {
        resetBtn.onclick = resetTaxCalculator;
    }

    if (saveCalculationBtnAlt) {
        saveCalculationBtnAlt.onclick = saveTaxCalculation;
    }

    if (refreshSavedBtn) {
        refreshSavedBtn.onclick = loadSavedCalculations;
    }

    // Load button to filter calculations by selected year
    if (loadSavedByYearBtn) {
        loadSavedByYearBtn.onclick = function() {
            console.log('Load button clicked');
            filterCalculationsByYear();
        };
    }

    // Update year/assessment display when year changes
    if (assessmentYearSelect) {
        assessmentYearSelect.addEventListener('change', function() {
            updateYearDisplay();
        });
        updateYearDisplay();
    }

    // Update monthly data table when start month changes
    if (startMonthSelect) {
        startMonthSelect.addEventListener('change', populateMonthlyDataTable);
    }

    // Initial table population
    populateMonthlyDataTable();

    // Load all saved calculations on page load
    loadSavedCalculations();
}

function updateYearDisplay() {
    const assessmentYear = document.getElementById('assessmentYear').value;
    const yaDisplay = document.getElementById('yaDisplay');
    if (yaDisplay) {
        yaDisplay.textContent = assessmentYear;
    }
}

function filterCalculationsByYear() {
    const selectedYear = document.getElementById('assessmentYear').value;

    console.log('Loading calculations for year:', selectedYear);

    // Use backend filtering for better performance
    showLoading();

    fetch(`/api/tax-calculations?year=${encodeURIComponent(selectedYear)}`)
    .then(response => response.json())
    .then(calculations => {
        console.log('Filtered calculations from backend:', calculations);

        // Check if it's an error response
        if (calculations.error) {
            hideLoading();
            console.error('API returned error:', calculations.error);
            showToast('Error: ' + calculations.error, 'danger');
            displaySavedCalculations([], selectedYear);
            return;
        }

        const calculationsList = Array.isArray(calculations) ? calculations : [];

        // Display filtered calculations
        displaySavedCalculations(calculationsList, selectedYear);

        // Auto-load the active calculation or the most recent one
        if (calculationsList.length > 0) {
            // Find active calculation
            const activeCalc = calculationsList.find(calc => calc.is_active);
            const calcToLoad = activeCalc || calculationsList[0]; // Use active or first (most recent)

            console.log(`Auto-loading ${activeCalc ? 'active' : 'most recent'} calculation: ${calcToLoad.calculation_name}`);

            // Load the calculation (this will call hideLoading())
            loadCalculation(calcToLoad.id);
        } else {
            hideLoading();
            showToast(`No calculations found for ${selectedYear}`, 'info');
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error filtering calculations:', error);
        showToast('Failed to load calculations. Check console for details.', 'danger');
        displaySavedCalculations([], selectedYear);
    });
}

function populateMonthlyDataTable() {
    const tbody = document.getElementById('monthlyDataBody');
    if (!tbody) return;

    const startMonthIndex = parseInt(document.getElementById('startMonth').value) || 0;
    const defaultSalaryRate = 0;
    const defaultSalary = 0;

    let html = '';
    for (let i = 0; i < 12; i++) {
        const monthIndex = (startMonthIndex + i) % 12;
        const monthName = monthNames[monthIndex];
        const collapseId = `month-${monthIndex}-collapse`;

        html += `
            <tr class="month-header-row" data-bs-toggle="collapse" data-bs-target="#${collapseId}" role="button">
                <td colspan="5" class="month-header">
                    <i class="fas fa-chevron-right me-2 month-chevron"></i>
                    <strong>${monthName}</strong>
                    <span class="opacity-75 ms-2 month-summary" id="summary-${monthIndex}"></span>
                </td>
            </tr>
            <tr class="collapse month-detail-row" id="${collapseId}">
                <td colspan="5" class="p-0">
                    <div class="month-detail-content">
                        <div class="p-3">
                            <div class="row g-3">
                                <!-- Salary Section Card -->
                                <div class="col-md-6">
                                    <div class="card">
                                        <div class="card-body">
                                            <h6 class="card-subtitle mb-3">Monthly Salary</h6>
                                            <div class="input-group input-group-sm">
                                                <span class="input-group-text">$</span>
                                                <input type="number" class="form-control month-salary"
                                                       data-month="${monthIndex}"
                                                       placeholder="6000"
                                                       value="${defaultSalary}"
                                                       step="100"
                                                       min="0">
                                                <span class="input-group-text">USD</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <!-- Exchange Rate Section Card -->
                                <div class="col-md-6">
                                    <div class="card">
                                        <div class="card-body">
                                            <h6 class="card-subtitle mb-3">Exchange Rate</h6>
                                            <div class="input-group input-group-sm mb-2">
                                                <input type="number" class="form-control month-salary-rate"
                                                       data-month="${monthIndex}"
                                                       placeholder="299"
                                                       value="${defaultSalaryRate}"
                                                       step="0.01"
                                                       min="0">
                                                <span class="input-group-text">LKR</span>
                                            </div>
                                            <div class="input-group input-group-sm mb-2">
                                                <input type="date" class="form-control month-salary-rate-date"
                                                       data-month="${monthIndex}"
                                                       placeholder="Select date">
                                                <button type="button" class="btn btn-sm btn-outline-secondary fetch-salary-rate-btn"
                                                        data-month="${monthIndex}"
                                                        title="Auto-fetch rate from database">
                                                    <i class="fas fa-sync-alt"></i>
                                                </button>
                                            </div>
                                            <small class="d-block" style="opacity: 0.65;">Select date to auto-fetch rate</small>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <!-- Bonuses Section -->
                            <div class="mt-3">
                                <div class="card">
                                    <div class="card-body">
                                        <div class="d-flex justify-content-between align-items-center mb-3">
                                            <h6 class="card-subtitle mb-0">Bonuses</h6>
                                            <button type="button" class="btn btn-sm btn-outline-primary add-bonus-btn"
                                                    data-month="${monthIndex}">
                                                <i class="fas fa-plus me-1"></i>Add Bonus
                                            </button>
                                        </div>
                                        <div class="bonuses-container" data-month="${monthIndex}">
                                            <!-- Bonuses will be added dynamically here -->
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </td>
            </tr>
        `;
    }

    tbody.innerHTML = html;

    // Add event listeners to rotate chevron icons
    document.querySelectorAll('.month-header-row').forEach(row => {
        row.addEventListener('click', function() {
            const chevron = this.querySelector('.month-chevron');
            chevron.classList.toggle('fa-chevron-right');
            chevron.classList.toggle('fa-chevron-down');
        });
    });

    // Add event listeners for "Add Bonus" buttons
    document.querySelectorAll('.add-bonus-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation(); // Prevent collapse toggle
            const monthIndex = parseInt(this.getAttribute('data-month'));
            addBonusEntry(monthIndex);
        });
    });

    // Add event listeners for "Fetch Salary Rate" buttons
    document.querySelectorAll('.fetch-salary-rate-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation(); // Prevent collapse toggle
            const monthIndex = parseInt(this.getAttribute('data-month'));
            fetchExchangeRateForSalary(monthIndex);
        });
    });
}

// Helper function to add a bonus entry
function addBonusEntry(monthIndex, bonusAmount = 0, bonusRate = 299, bonusDate = '') {
    const container = document.querySelector(`.bonuses-container[data-month="${monthIndex}"]`);
    if (!container) return;

    const bonusId = `bonus-${monthIndex}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    const bonusHtml = `
        <div class="bonus-entry mb-3" data-bonus-id="${bonusId}">
            <div class="card">
                <div class="card-body">
                    <div class="row g-3 align-items-start">
                        <div class="col-md-4">
                            <label class="form-label small mb-2" style="opacity: 0.65;">Amount</label>
                            <div class="input-group input-group-sm">
                                <span class="input-group-text">$</span>
                                <input type="number" class="form-control month-bonus"
                                       data-month="${monthIndex}"
                                       placeholder="0"
                                       value="${bonusAmount}"
                                       step="100"
                                       min="0">
                                <span class="input-group-text">USD</span>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label small mb-2" style="opacity: 0.65;">Exchange Rate</label>
                            <div class="input-group input-group-sm mb-2">
                                <input type="number" class="form-control month-bonus-rate"
                                       data-month="${monthIndex}"
                                       placeholder="299"
                                       value="${bonusRate}"
                                       step="0.01"
                                       min="0">
                                <span class="input-group-text">LKR</span>
                            </div>
                            <div class="input-group input-group-sm">
                                <input type="date" class="form-control month-bonus-rate-date"
                                       data-month="${monthIndex}"
                                       data-bonus-id="${bonusId}"
                                       placeholder="Select date"
                                       value="${bonusDate}">
                                <button type="button" class="btn btn-sm btn-outline-secondary fetch-bonus-rate-btn"
                                        data-month="${monthIndex}"
                                        data-bonus-id="${bonusId}"
                                        title="Auto-fetch rate from database">
                                    <i class="fas fa-sync-alt"></i>
                                </button>
                            </div>
                        </div>
                        <div class="col-md-2 d-flex align-items-start" style="padding-top: 1.9rem;">
                            <button type="button" class="btn btn-sm btn-outline-danger remove-bonus-btn w-100"
                                    data-bonus-id="${bonusId}"
                                    title="Remove bonus">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', bonusHtml);

    // Add event listener for remove button
    const removeBtn = container.querySelector(`[data-bonus-id="${bonusId}"] .remove-bonus-btn`);
    removeBtn.addEventListener('click', function(e) {
        e.stopPropagation(); // Prevent collapse toggle
        const bonusEntry = this.closest('.bonus-entry');
        bonusEntry.remove();
    });

    // Add event listener for fetch bonus rate button
    const fetchBtn = container.querySelector(`[data-bonus-id="${bonusId}"] .fetch-bonus-rate-btn`);
    fetchBtn.addEventListener('click', function(e) {
        e.stopPropagation(); // Prevent collapse toggle
        const monthIndex = parseInt(this.getAttribute('data-month'));
        const bonusId = this.getAttribute('data-bonus-id');
        fetchExchangeRateForBonus(monthIndex, bonusId);
    });
}

// Function to fetch exchange rate for salary
async function fetchExchangeRateForSalary(monthIndex) {
    const dateInput = document.querySelector(`.month-salary-rate-date[data-month="${monthIndex}"]`);
    const rateInput = document.querySelector(`.month-salary-rate[data-month="${monthIndex}"]`);
    const fetchBtn = document.querySelector(`.fetch-salary-rate-btn[data-month="${monthIndex}"]`);

    const date = dateInput.value;
    if (!date) {
        showToast('Please select a date first', 'warning');
        return;
    }

    // Disable button and show loading state
    const originalHtml = fetchBtn.innerHTML;
    fetchBtn.disabled = true;
    fetchBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

    try {
        const response = await fetch(`/api/exchange-rate?date=${date}`);
        const data = await response.json();

        if (response.ok) {
            // Use the buy rate as the default rate
            rateInput.value = data.buy_rate.toFixed(2);

            let message = `Rate updated: ${data.buy_rate.toFixed(2)} LKR`;
            if (data.note) {
                message += ` (${data.note})`;
            }
            showToast(message, 'success');
        } else {
            showToast(data.error || 'Failed to fetch exchange rate', 'error');
        }
    } catch (error) {
        console.error('Error fetching exchange rate:', error);
        showToast('Network error: Unable to fetch exchange rate', 'error');
    } finally {
        // Re-enable button and restore icon
        fetchBtn.disabled = false;
        fetchBtn.innerHTML = originalHtml;
    }
}

// Function to fetch exchange rate for bonus
async function fetchExchangeRateForBonus(monthIndex, bonusId) {
    const dateInput = document.querySelector(`.month-bonus-rate-date[data-bonus-id="${bonusId}"]`);
    const rateInput = document.querySelector(`[data-bonus-id="${bonusId}"] .month-bonus-rate`);
    const fetchBtn = document.querySelector(`.fetch-bonus-rate-btn[data-bonus-id="${bonusId}"]`);

    const date = dateInput.value;
    if (!date) {
        showToast('Please select a date first', 'warning');
        return;
    }

    // Disable button and show loading state
    const originalHtml = fetchBtn.innerHTML;
    fetchBtn.disabled = true;
    fetchBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

    try {
        const response = await fetch(`/api/exchange-rate?date=${date}`);
        const data = await response.json();

        if (response.ok) {
            // Use the buy rate as the default rate
            rateInput.value = data.buy_rate.toFixed(2);

            let message = `Rate updated: ${data.buy_rate.toFixed(2)} LKR`;
            if (data.note) {
                message += ` (${data.note})`;
            }
            showToast(message, 'success');
        } else {
            showToast(data.error || 'Failed to fetch exchange rate', 'error');
        }
    } catch (error) {
        console.error('Error fetching exchange rate:', error);
        showToast('Network error: Unable to fetch exchange rate', 'error');
    } finally {
        // Re-enable button and restore icon
        fetchBtn.disabled = false;
        fetchBtn.innerHTML = originalHtml;
    }
}

function calculateMonthlyTax() {
    // Get form values
    const taxFreeThreshold = parseFloat(document.getElementById('taxFreeThreshold').value) || 1800000;
    const startMonthIndex = parseInt(document.getElementById('startMonth').value) || 0;

    // Read monthly salary and their exchange rates from table
    const salaryInputs = document.querySelectorAll('.month-salary');
    const salaryRateInputs = document.querySelectorAll('.month-salary-rate');
    const salaryRateDateInputs = document.querySelectorAll('.month-salary-rate-date');

    const monthlySalaries = {};
    const monthlySalaryRates = {};
    const monthlySalaryRateDates = {};
    const monthlyBonusesData = {}; // Will store array of {amount, rate, date} for each month

    salaryInputs.forEach(input => {
        const monthIndex = parseInt(input.getAttribute('data-month'));
        monthlySalaries[monthIndex] = parseFloat(input.value) || 0;
    });

    salaryRateInputs.forEach(input => {
        const monthIndex = parseInt(input.getAttribute('data-month'));
        monthlySalaryRates[monthIndex] = parseFloat(input.value) || 0;
    });

    salaryRateDateInputs.forEach(input => {
        const monthIndex = parseInt(input.getAttribute('data-month'));
        const dateValue = input.value || null;
        monthlySalaryRateDates[monthIndex] = dateValue;
        if (dateValue) {
            console.log(`Collecting date for month ${monthIndex}: ${dateValue}`);
        }
    });

    // Collect all bonuses for each month
    const bonusContainers = document.querySelectorAll('.bonuses-container');
    bonusContainers.forEach(container => {
        const monthIndex = parseInt(container.getAttribute('data-month'));
        const bonusEntries = container.querySelectorAll('.bonus-entry');

        monthlyBonusesData[monthIndex] = [];
        bonusEntries.forEach(entry => {
            const bonusInput = entry.querySelector('.month-bonus');
            const bonusRateInput = entry.querySelector('.month-bonus-rate');
            const bonusRateDateInput = entry.querySelector('.month-bonus-rate-date');

            const amount = parseFloat(bonusInput.value) || 0;
            const rate = parseFloat(bonusRateInput.value) || 0;
            const date = bonusRateDateInput ? (bonusRateDateInput.value || null) : null;

            if (amount > 0) {
                monthlyBonusesData[monthIndex].push({ amount, rate, date });
            }
        });
    });

    // Validate that all months have valid salary exchange rates
    let hasInvalidRates = false;
    Object.values(monthlySalaryRates).forEach(rate => {
        if (rate <= 0) hasInvalidRates = true;
    });

    if (hasInvalidRates) {
        showToast('Please enter valid salary exchange rates for all months', 'warning');
        return;
    }

    // Calculate for 12 months
    const monthlyData = [];
    let cumulativeIncome = 0;
    let previousTaxLiability = 0;
    let totalUSD = 0;
    let totalConverted = 0;

    for (let i = 0; i < 12; i++) {
        const monthIndex = (startMonthIndex + i) % 12;
        const monthName = monthNames[monthIndex];

        const salaryUSD = monthlySalaries[monthIndex] || 0;
        const salaryRate = monthlySalaryRates[monthIndex] || 0;

        // Calculate total bonuses for this month
        let totalBonusUSD = 0;
        let totalBonusLKR = 0;
        const bonuses = monthlyBonusesData[monthIndex] || [];
        bonuses.forEach(bonus => {
            totalBonusUSD += bonus.amount;
            totalBonusLKR += bonus.amount * bonus.rate;
        });

        // Calculate FC receipts for this month
        const fcReceiptsUSD = salaryUSD + totalBonusUSD;
        const fcReceiptsLKR = (salaryUSD * salaryRate) + totalBonusLKR;

        // Update cumulative income
        cumulativeIncome += fcReceiptsLKR;

        // Calculate total tax liability using progressive brackets
        // Bracket 1: Up to 1,800,000 - 0% (Relief)
        // Bracket 2: 1,800,001 to 2,800,000 (next 1,000,000) - 6%
        // Bracket 3: Above 2,800,000 - 15%
        let totalTaxLiability = 0;

        if (cumulativeIncome > 1_800_000) {
            if (cumulativeIncome <= 2_800_000) {
                // Income is in the 6% bracket
                totalTaxLiability = (cumulativeIncome - 1_800_000) * 0.06;
            } else {
                // Income exceeds 2,800,000
                // Tax on first 1,000,000 above 1,800,000 (up to 2,800,000): 6%
                totalTaxLiability = 1_000_000 * 0.06;  // LKR 60,000
                // Tax on amount above 2,800,000: 15%
                totalTaxLiability += (cumulativeIncome - 2_800_000) * 0.15;
            }
        }

        // Calculate monthly payment (difference from previous month)
        const monthlyPayment = Math.max(0, totalTaxLiability - previousTaxLiability);

        // Store data
        monthlyData.push({
            month: monthName,
            fcReceiptsUSD: fcReceiptsUSD,
            fcReceiptsLKR: fcReceiptsLKR,
            cumulativeIncome: cumulativeIncome,
            totalTaxLiability: totalTaxLiability,
            monthlyPayment: monthlyPayment
        });

        // Update for next iteration
        previousTaxLiability = totalTaxLiability;
        totalUSD += fcReceiptsUSD;
        totalConverted += fcReceiptsLKR;
    }

    // Update table
    updateTaxScheduleTable(monthlyData);

    // Update totals
    document.getElementById('totalUSD').textContent = `$${totalUSD.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
    document.getElementById('totalConverted').textContent = formatCurrency(totalConverted);
    document.getElementById('totalTaxLiability').textContent = formatCurrency(previousTaxLiability);
    document.getElementById('totalMonthlyPayments').textContent = formatCurrency(previousTaxLiability);

    // Update summary cards
    document.getElementById('annualIncomeSummary').textContent = formatCurrency(cumulativeIncome);
    document.getElementById('taxFreeAmountSummary').textContent = formatCurrency(taxFreeThreshold);
    document.getElementById('totalTaxSummary').textContent = formatCurrency(previousTaxLiability);

    const effectiveRate = cumulativeIncome > 0 ? (previousTaxLiability / cumulativeIncome * 100) : 0;
    document.getElementById('effectiveTaxRateSummary').textContent = `${effectiveRate.toFixed(2)}%`;

    // Store calculation data for saving (ONLY input data, calculations are computed on-the-fly)
    lastCalculationData = {
        assessment_year: document.getElementById('assessmentYear').value,
        tax_rate: 0, // Using progressive brackets (0%, 6%, 15%), not a single rate
        tax_free_threshold: taxFreeThreshold,
        start_month: startMonthIndex,
        monthly_data: monthlyData.map((row, index) => {
            const actualMonthIndex = (startMonthIndex + index) % 12;
            const bonuses = monthlyBonusesData[actualMonthIndex] || [];
            const salaryRateDate = monthlySalaryRateDates[actualMonthIndex] || null;

            // Save ONLY income input data (salaries, rates, bonuses, and dates)
            const monthDataEntry = {
                month_index: index,
                month: row.month,
                salary_usd: monthlySalaries[actualMonthIndex] || 0,
                salary_rate: monthlySalaryRates[actualMonthIndex] || 0,
                salary_rate_date: salaryRateDate,
                bonuses: bonuses  // Array format: [{amount: 5000, rate: 299, date: '2025-11-21'}, ...]
            };

            if (salaryRateDate) {
                console.log(`Saving month ${actualMonthIndex} (${row.month}) with date: ${salaryRateDate}`);
            }

            return monthDataEntry;
        })
    };

    console.log('Full calculation data to be saved:', JSON.stringify(lastCalculationData.monthly_data, null, 2));

    // Show save section
    const saveSection = document.getElementById('saveCalculationSection');
    if (saveSection) {
        saveSection.style.display = 'block';
        // Auto-generate calculation name
        document.getElementById('calculationName').value = `Tax Calculation ${lastCalculationData.assessment_year}`;
    }

    // Show summary cards
    const summaryCards = document.getElementById('taxSummaryCards');
    if (summaryCards) {
        summaryCards.style.display = 'flex';
    }

    // Show table footer
    const tfoot = document.querySelector('#taxScheduleTable tfoot');
    if (tfoot) {
        tfoot.style.display = 'table-footer-group';
    }

    showToast('Tax schedule calculated successfully', 'success');
}

function updateTaxScheduleTable(monthlyData) {
    const tbody = document.getElementById('taxScheduleBody');
    if (!tbody) return;

    let html = '';
    let quarterlyUSD = 0;
    let quarterlyLKR = 0;
    let quarterlyPayment = 0;

    monthlyData.forEach((row, index) => {
        // Add month row
        html += `
            <tr>
                <td>${row.month}</td>
                <td class="text-end">$${row.fcReceiptsUSD.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
                <td class="text-end">${formatCurrency(row.fcReceiptsLKR)}</td>
                <td class="text-end">${formatCurrency(row.cumulativeIncome)}</td>
                <td class="text-end">${formatCurrency(row.totalTaxLiability)}</td>
                <td class="text-end fw-bold text-danger">${formatCurrency(row.monthlyPayment)}</td>
            </tr>
        `;

        // Accumulate quarterly totals
        quarterlyUSD += row.fcReceiptsUSD;
        quarterlyLKR += row.fcReceiptsLKR;
        quarterlyPayment += row.monthlyPayment;

        const monthNumber = index + 1;

        // Add quarterly summary after every 3 months
        if (monthNumber % 3 === 0) {
            const quarterNum = monthNumber / 3;
            html += `
                <tr class="table-active border-top border-bottom border-2">
                    <td class="fw-bold"><i class="fas fa-chart-bar me-2"></i>Q${quarterNum} Total</td>
                    <td class="text-end fw-bold">$${quarterlyUSD.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
                    <td class="text-end fw-bold">${formatCurrency(quarterlyLKR)}</td>
                    <td class="text-end">-</td>
                    <td class="text-end">-</td>
                    <td class="text-end fw-bold text-primary">${formatCurrency(quarterlyPayment)}</td>
                </tr>
            `;
            // Reset quarterly totals
            quarterlyUSD = 0;
            quarterlyLKR = 0;
            quarterlyPayment = 0;
        }

        // Add half-year summary after 6 months
        if (monthNumber === 6) {
            const halfYearUSD = monthlyData.slice(0, 6).reduce((sum, m) => sum + m.fcReceiptsUSD, 0);
            const halfYearLKR = monthlyData.slice(0, 6).reduce((sum, m) => sum + m.fcReceiptsLKR, 0);
            const halfYearPayment = monthlyData.slice(0, 6).reduce((sum, m) => sum + m.monthlyPayment, 0);

            html += `
                <tr class="table-warning border-top border-bottom border-3">
                    <td class="fw-bold"><i class="fas fa-star me-2"></i>Half-Year Total</td>
                    <td class="text-end fw-bold">$${halfYearUSD.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</td>
                    <td class="text-end fw-bold">${formatCurrency(halfYearLKR)}</td>
                    <td class="text-end">-</td>
                    <td class="text-end">-</td>
                    <td class="text-end fw-bold text-success">${formatCurrency(halfYearPayment)}</td>
                </tr>
            `;
        }
    });

    tbody.innerHTML = html;
}

function resetTaxCalculator() {
    // Reset form fields
    document.getElementById('assessmentYear').value = '2024/2025';
    document.getElementById('taxFreeThreshold').value = '1800000';
    document.getElementById('startMonth').value = '0';

    // Repopulate monthly data table with default values
    populateMonthlyDataTable();

    // Reset results table
    const tbody = document.getElementById('taxScheduleBody');
    if (tbody) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center opacity-75 py-5">
                    <i class="fas fa-calculator fa-2x mb-2 d-block"></i>
                    Click "Calculate Tax" to generate schedule
                </td>
            </tr>
        `;
    }

    // Reset totals
    document.getElementById('totalUSD').textContent = '$0';
    document.getElementById('totalConverted').textContent = 'LKR 0';
    document.getElementById('totalTaxLiability').textContent = 'LKR 0';
    document.getElementById('totalMonthlyPayments').textContent = 'LKR 0';

    // Reset summary cards
    document.getElementById('annualIncomeSummary').textContent = 'LKR 0';
    document.getElementById('taxFreeAmountSummary').textContent = 'LKR 360,000';
    document.getElementById('totalTaxSummary').textContent = 'LKR 0';
    document.getElementById('effectiveTaxRateSummary').textContent = '0%';

    // Update displays
    updateYearDisplay();

    // Hide save section
    const saveSection = document.getElementById('saveCalculationSection');
    if (saveSection) {
        saveSection.style.display = 'none';
    }

    // Hide summary cards
    const summaryCards = document.getElementById('taxSummaryCards');
    if (summaryCards) {
        summaryCards.style.display = 'none';
    }

    // Hide table footer
    const tfoot = document.querySelector('#taxScheduleTable tfoot');
    if (tfoot) {
        tfoot.style.display = 'none';
    }

    lastCalculationData = null;

    showToast('Tax calculator reset', 'info');
}

// ================================
// SAVE AND LOAD CALCULATIONS
// ================================

function saveTaxCalculation() {
    if (!lastCalculationData) {
        showToast('Please calculate tax first before saving', 'warning');
        return;
    }

    const calculationName = document.getElementById('calculationName').value.trim();
    if (!calculationName) {
        showToast('Please enter a name for this calculation', 'warning');
        return;
    }

    const setAsActive = document.getElementById('setAsActive')?.checked || false;

    const dataToSave = {
        ...lastCalculationData,
        calculation_name: calculationName,
        is_active: setAsActive
    };

    console.log('=== SAVING CALCULATION ===');
    console.log('Data to save:', dataToSave);
    console.log('Monthly data being saved:', dataToSave.monthly_data);

    showLoading();

    fetch('/api/tax-calculations', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(dataToSave)
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.error) {
            showToast(data.error, 'danger');
        } else {
            showToast('Tax calculation saved successfully!', 'success');
            // Reload saved calculations list
            loadSavedCalculations();
            // Hide save section
            document.getElementById('saveCalculationSection').style.display = 'none';
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error saving calculation:', error);
        showToast('Failed to save calculation', 'danger');
    });
}

function loadSavedCalculations() {
    console.log('Loading saved calculations from API...');
    showLoading();

    fetch('/api/tax-calculations')
    .then(response => {
        console.log('API response status:', response.status);
        return response.json();
    })
    .then(calculations => {
        hideLoading();
        console.log('Received calculations from API:', calculations);

        // Check if it's an error response
        if (calculations.error) {
            console.error('API returned error:', calculations.error);
            showToast('Error: ' + calculations.error, 'danger');
            allSavedCalculations = [];
            displaySavedCalculations([], null);
            return;
        }

        // Store all calculations globally
        allSavedCalculations = Array.isArray(calculations) ? calculations : [];
        console.log('Stored calculations:', allSavedCalculations.length, 'items');

        // Display all calculations (not filtered)
        displaySavedCalculations(allSavedCalculations, null);
    })
    .catch(error => {
        hideLoading();
        console.error('Error loading calculations:', error);
        showToast('Failed to load saved calculations. Check console for details.', 'danger');
        allSavedCalculations = [];
        displaySavedCalculations([], null);
    });
}

function displaySavedCalculations(calculations, filterYear = null) {
    const listContainer = document.getElementById('savedCalculationsList');
    if (!listContainer) return;

    if (!calculations || calculations.length === 0) {
        const message = filterYear
            ? `No saved calculations found for ${filterYear}. <a href="#" onclick="showAllCalculations(); return false;" class="alert-link">Show all calculations</a>`
            : 'No saved calculations yet. Calculate and save your tax to see it here.';

        listContainer.innerHTML = `
            <p class="opacity-75 text-center py-4">
                <i class="fas fa-info-circle me-2"></i>${message}
            </p>
        `;
        return;
    }

    // Show filter info if filtering
    let headerHtml = '';
    if (filterYear && allSavedCalculations.length > calculations.length) {
        headerHtml = `
            <div class="alert alert-info mb-3">
                <i class="fas fa-filter me-2"></i>Showing ${calculations.length} calculation(s) for ${filterYear}.
                <a href="#" onclick="showAllCalculations(); return false;" class="alert-link">Show all ${allSavedCalculations.length} calculations</a>
            </div>
        `;
    }

    let html = headerHtml + '<div class="list-group">';
    calculations.forEach(calc => {
        const createdDate = new Date(calc.created_at).toLocaleDateString();
        const isActive = calc.is_active || false;
        const activeClass = isActive ? 'border-success' : '';

        html += `
            <div class="list-group-item list-group-item-action calculation-item mb-2 ${activeClass}">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <h6 class="mb-1">
                            ${calc.calculation_name}
                            ${isActive ? '<span class="badge bg-success ms-2">Active</span>' : ''}
                        </h6>
                        <p class="mb-1 small">
                            <span class="badge bg-primary me-2">${calc.assessment_year}</span>
                            <span class="opacity-75">Saved: ${createdDate}</span>
                        </p>
                        <div class="row mt-2">
                            <div class="col-md-6">
                                <small class="opacity-75">Tax Structure:</small><br>
                                <strong>Progressive Brackets</strong>
                            </div>
                            <div class="col-md-6">
                                <small class="opacity-75">Tax-Free Threshold:</small><br>
                                <strong>${formatCurrency(calc.tax_free_threshold)}</strong>
                            </div>
                        </div>
                        <p class="mb-0 mt-2"><small class="opacity-75"><i class="fas fa-info-circle me-1"></i>Tax totals will be calculated when you load this</small></p>
                    </div>
                    <div class="ms-3 d-flex flex-column gap-1">
                        <button class="btn btn-sm btn-outline-primary" onclick="loadCalculation(${calc.id})" title="Load this calculation">
                            <i class="fas fa-download"></i>
                        </button>
                        ${!isActive ? `<button class="btn btn-sm btn-outline-success" onclick="setActiveCalculation(${calc.id})" title="Set as active">
                            <i class="fas fa-star"></i>
                        </button>` : ''}
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteCalculation(${calc.id})" title="Delete this calculation">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    });
    html += '</div>';

    listContainer.innerHTML = html;
}

function showAllCalculations() {
    // Reload all calculations from backend
    loadSavedCalculations();
}

function setActiveCalculation(calculationId) {
    if (!confirm('Set this calculation as active for its assessment year?')) {
        return;
    }

    showLoading();

    fetch(`/api/tax-calculations/${calculationId}/set-active`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        // Check if feature is not implemented (501)
        if (response.status === 501) {
            return response.json().then(data => {
                hideLoading();
                showToast(data.error || 'This feature requires a database migration.', 'warning');
                return null;
            });
        }
        return response.json();
    })
    .then(data => {
        if (!data) return; // Already handled 501 case

        hideLoading();
        if (data.error) {
            showToast(data.error, 'danger');
        } else {
            showToast(`Calculation set as active for ${data.assessment_year}!`, 'success');
            // Reload the calculations list to reflect the change
            loadSavedCalculations();
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error setting active calculation:', error);
        showToast('Failed to set active calculation', 'danger');
    });
}

function loadCalculation(calculationId) {
    showLoading();

    fetch(`/api/tax-calculations/${calculationId}`)
    .then(response => response.json())
    .then(calc => {
        hideLoading();

        if (calc.error) {
            showToast(calc.error, 'danger');
            return;
        }

        console.log('=== LOADING CALCULATION ===');
        console.log('ID:', calc.id, '| Name:', calc.calculation_name);
        console.log('Year:', calc.assessment_year, '| Threshold:', calc.tax_free_threshold);
        console.log('Start month:', calc.start_month);
        console.log('Monthly data entries:', calc.monthly_data ? calc.monthly_data.length : 0);

        // Load values into form fields
        document.getElementById('assessmentYear').value = calc.assessment_year;
        // Tax rate is now hardcoded in progressive brackets, not loaded from saved data
        document.getElementById('taxFreeThreshold').value = calc.tax_free_threshold;
        document.getElementById('startMonth').value = calc.start_month;

        // Update year display
        updateYearDisplay();

        // Get monthly data (already parsed by backend)
        const monthlyData = calc.monthly_data || [];
        if (monthlyData.length > 0) {
            console.log('Sample monthly entry:', monthlyData[0]);
        }

        // Repopulate monthly table with current start month (this creates fresh input fields)
        populateMonthlyDataTable();

        // Clear any existing bonus data
        monthlyBonusesData = {};

        // Create a map of actual month index to salary, salary rate, and bonuses
        const monthDataMap = {};
        monthlyData.forEach((month) => {
            // Calculate the actual month index from start_month + month_index
            const actualMonthIndex = (calc.start_month + month.month_index) % 12;

            monthDataMap[actualMonthIndex] = {
                salary_usd: month.salary_usd || 0,
                salary_rate: month.salary_rate || 0,
                salary_rate_date: month.salary_rate_date || null,
                bonuses: month.bonuses || []  // Array of {amount, rate, date}
            };
        });

        console.log(`Mapped ${Object.keys(monthDataMap).length} months from saved data`);
        console.log('Sample month data:', monthDataMap[0] || monthDataMap[Object.keys(monthDataMap)[0]]);

        // Wait for DOM to update after populateMonthlyDataTable()
        // This ensures the date inputs are fully rendered before we try to set their values
        setTimeout(() => {
            // Load salary and salary rate by matching data-month attribute
            const salaryInputs = document.querySelectorAll('.month-salary');
            const salaryRateInputs = document.querySelectorAll('.month-salary-rate');
            const salaryRateDateInputs = document.querySelectorAll('.month-salary-rate-date');

            console.log(`Found ${salaryInputs.length} salary inputs, ${salaryRateInputs.length} salary rate inputs, and ${salaryRateDateInputs.length} date inputs`);

            let salariesSet = 0, ratesSet = 0, datesSet = 0;
            salaryInputs.forEach(input => {
                const monthIndex = parseInt(input.getAttribute('data-month'));
                if (monthDataMap[monthIndex]) {
                    input.value = monthDataMap[monthIndex].salary_usd;
                    salariesSet++;
                }
            });

            salaryRateInputs.forEach(input => {
                const monthIndex = parseInt(input.getAttribute('data-month'));
                if (monthDataMap[monthIndex]) {
                    input.value = monthDataMap[monthIndex].salary_rate;
                    ratesSet++;
                }
            });

            salaryRateDateInputs.forEach(input => {
                const monthIndex = parseInt(input.getAttribute('data-month'));
                const monthData = monthDataMap[monthIndex];
                console.log(`Month ${monthIndex}: salary_rate_date =`, monthData ? monthData.salary_rate_date : 'no data');
                if (monthData && monthData.salary_rate_date) {
                    input.value = monthData.salary_rate_date;
                    console.log(`Set date input for month ${monthIndex} to ${monthData.salary_rate_date}`);
                    datesSet++;
                }
            });

            console.log(`Set ${salariesSet} salaries, ${ratesSet} exchange rates, and ${datesSet} rate dates`);

            // Load bonuses for each month
            let bonusesLoaded = 0;
            Object.keys(monthDataMap).forEach(monthIndex => {
                const bonuses = monthDataMap[monthIndex].bonuses || [];

                // Add each bonus entry
                bonuses.forEach(bonus => {
                    if (bonus.amount > 0) {
                        const bonusDate = bonus.date || '';
                        console.log(`Loading bonus for month ${monthIndex}: amount=${bonus.amount}, rate=${bonus.rate}, date=${bonusDate}`);
                        addBonusEntry(parseInt(monthIndex), bonus.amount, bonus.rate, bonusDate);
                        bonusesLoaded++;
                    }
                });
            });

            console.log(`Loaded ${bonusesLoaded} bonus entries`);

            console.log('Form fields populated, recalculating tax schedule...');

            // Recalculate tax schedule with loaded data
            calculateMonthlyTax();
        }, 100); // 100ms delay to ensure DOM is updated

        showToast(`Loaded: ${calc.calculation_name}`, 'success');

        // Scroll to top
        window.scrollTo({ top: 0, behavior: 'smooth' });
    })
    .catch(error => {
        hideLoading();
        console.error('Error loading calculation:', error);
        showToast('Failed to load calculation', 'danger');
    });
}

function deleteCalculation(calculationId) {
    if (!confirm('Are you sure you want to delete this calculation? This action cannot be undone.')) {
        return;
    }

    showLoading();

    fetch(`/api/tax-calculations/${calculationId}`, {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.error) {
            showToast(data.error, 'danger');
        } else {
            showToast('Calculation deleted successfully', 'success');
            loadSavedCalculations();
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error deleting calculation:', error);
        showToast('Failed to delete calculation', 'danger');
    });
}

// Note: formatCurrency, formatDate, showLoading, hideLoading, showToast
// are defined in base.html and available globally
