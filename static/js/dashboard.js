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
    forecastReport: null,
    paymentMethod: null,
    spendingHeatmap: null,
    yearOverYear: null,
    incomeSources: null,
    transactionDone: null,
    transactionPaid: null,
    expenseGrowth: null,
    savingsRate: null
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
    notes: '',
    caseSensitive: false,
    excludeWeekends: false
};
let savedFilterPresets = JSON.parse(localStorage.getItem('filterPresets') || '[]');
let recentFilters = JSON.parse(localStorage.getItem('recentFilters') || '[]');
let reportFiltersInitialized = false;
let filterDropdownsInitialized = false;
let filterSearchListenersInitialized = false; // Track if filter search listeners are initialized
let loadedReportTabs = new Set(); // Track which report tabs have been loaded
let reportTabsInitialized = false; // Track if tab listeners are initialized
let scannedBillContent = null; // Store scanned bill content temporarily
let capturedBillImages = []; // Store all captured bill images for upload
let uploadMode = 'sequential'; // Upload mode: 'sequential' (one-by-one) or 'batch' (all at once)

// --- Client-side file compression for Vercel's 4.5 MB body limit ---
const UPLOAD_MAX_BYTES = 4 * 1024 * 1024; // 4 MB target (leaves headroom for form overhead)

/**
 * Compress an image file using Canvas.
 * Returns a Blob ≤ targetBytes (JPEG).
 */
async function compressImageFile(file, targetBytes = UPLOAD_MAX_BYTES) {
    const bitmap = await createImageBitmap(file);
    let { width, height } = bitmap;

    // Scale down so longest side ≤ 2000 px
    const maxDim = 2000;
    if (width > maxDim || height > maxDim) {
        const ratio = Math.min(maxDim / width, maxDim / height);
        width = Math.round(width * ratio);
        height = Math.round(height * ratio);
    }

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(bitmap, 0, 0, width, height);

    // Try decreasing quality until under target
    for (let q = 0.85; q >= 0.3; q -= 0.1) {
        const blob = await new Promise(r => canvas.toBlob(r, 'image/jpeg', q));
        if (blob.size <= targetBytes) return blob;
    }
    // Return lowest quality attempt
    return await new Promise(r => canvas.toBlob(r, 'image/jpeg', 0.3));
}

/**
 * Render the first page of a PDF to a JPEG image using pdf.js.
 * Falls back to sending the original if pdf.js is unavailable.
 */
async function compressPdfFile(file, targetBytes = UPLOAD_MAX_BYTES) {
    if (typeof pdfjsLib === 'undefined') {
        console.warn('pdf.js not loaded – sending PDF as-is');
        return file;
    }

    const arrayBuffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;

    // Render each page to canvas and collect images
    // For bill scanning, first page is usually sufficient
    const page = await pdf.getPage(1);
    const scale = 2; // 2x for readability
    const viewport = page.getViewport({ scale });

    const canvas = document.createElement('canvas');
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext('2d');
    await page.render({ canvasContext: ctx, viewport }).promise;

    for (let q = 0.85; q >= 0.3; q -= 0.1) {
        const blob = await new Promise(r => canvas.toBlob(r, 'image/jpeg', q));
        if (blob.size <= targetBytes) return blob;
    }
    return await new Promise(r => canvas.toBlob(r, 'image/jpeg', 0.3));
}

/**
 * Compress a file (image or PDF) if it exceeds the upload limit.
 * Returns { fileToSend, wasCompressed }.
 */
async function compressFileForUpload(file) {
    // For PDFs, only compress if > 10MB (Gemini handles multi-page PDFs well)
    const PDF_THRESHOLD = 10 * 1024 * 1024; // 10 MB

    if (file.type === 'application/pdf') {
        if (file.size <= PDF_THRESHOLD) {
            return { fileToSend: file, wasCompressed: false };
        }
        // For very large PDFs (>10MB), convert to JPEG as last resort
        console.log(`Large PDF ${file.name} is ${(file.size / (1024*1024)).toFixed(1)} MB – converting to image…`);
    } else {
        // For images, compress if > 4MB
        if (file.size <= UPLOAD_MAX_BYTES) {
            return { fileToSend: file, wasCompressed: false };
        }
        console.log(`Image ${file.name} is ${(file.size / (1024*1024)).toFixed(1)} MB – compressing…`);
    }

    try {
        let blob;
        if (file.type === 'application/pdf') {
            blob = await compressPdfFile(file);
        } else {
            blob = await compressImageFile(file);
        }

        // Build a new File so FormData gets a proper filename
        const ext = file.type === 'application/pdf' ? '.jpg' : '.' + (file.name.split('.').pop() || 'jpg');
        const baseName = file.name.replace(/\.[^.]+$/, '');
        const newName = file.type === 'application/pdf'
            ? baseName + '_scan.jpg'
            : baseName + ext;
        const compressed = new File([blob], newName, { type: blob.type });

        console.log(`Compressed: ${(file.size / (1024*1024)).toFixed(1)} MB → ${(compressed.size / (1024*1024)).toFixed(1)} MB`);
        return { fileToSend: compressed, wasCompressed: true };
    } catch (err) {
        console.error('Compression failed, sending original:', err);
        return { fileToSend: file, wasCompressed: false };
    }
}

// Helper function to check if two item names are similar (handles OCR errors)
function areItemsSimilar(name1, name2) {
    const n1 = name1.toLowerCase().trim();
    const n2 = name2.toLowerCase().trim();

    // Exact match
    if (n1 === n2) return true;

    // One name is substring of another
    if (n1.includes(n2) || n2.includes(n1)) return true;

    // Word-based similarity
    const words1 = new Set(n1.split(/\s+/));
    const words2 = new Set(n2.split(/\s+/));

    const minWords = Math.min(words1.size, words2.size);

    if (minWords <= 2) {
        // For short names, require all words to overlap
        const overlap = [...words1].filter(w => words2.has(w)).length;
        return overlap >= minWords;
    } else {
        // For longer names, require 70% word overlap
        const overlap = [...words1].filter(w => words2.has(w)).length;
        const similarity = overlap / Math.max(words1.size, words2.size);
        return similarity >= 0.7;
    }
}

// Display bill breakdown with discounts
function displayBillBreakdown(result) {
    const billBreakdown = document.getElementById('billBreakdown');
    const billBreakdownContent = document.getElementById('billBreakdownContent');

    if (!billBreakdown || !billBreakdownContent) return;

    // Only show if there are discounts or subtotal
    const hasDiscounts = result.discounts && result.discounts.length > 0;
    const hasSubtotal = parseFloat(result.subtotal || 0) > 0;

    if (!hasDiscounts && !hasSubtotal) {
        billBreakdown.style.display = 'none';
        return;
    }

    let breakdownHtml = '';

    // Show subtotal if available and different from total
    if (hasSubtotal && parseFloat(result.subtotal) !== parseFloat(result.amount)) {
        breakdownHtml += `<div class="d-flex justify-content-between mb-1">
            <span>Subtotal:</span>
            <span>රු ${parseFloat(result.subtotal).toFixed(2)}</span>
        </div>`;
    }

    // Show summary discounts
    if (hasDiscounts) {
        result.discounts.forEach((discount, index) => {
            const description = discount.description || `Discount ${index + 1}`;
            const amount = parseFloat(discount.amount || 0);
            breakdownHtml += `<div class="d-flex justify-content-between mb-1" style="color: #28a745;">
                <span><i class="fas fa-tag me-1"></i>${description}:</span>
                <span>-රු ${amount.toFixed(2)}</span>
            </div>`;
        });
    }

    // Show final total
    breakdownHtml += `<div class="d-flex justify-content-between mt-2 pt-2" style="border-top: 1px solid #dee2e6; font-weight: bold;">
        <span>Final Total:</span>
        <span>රු ${parseFloat(result.amount).toFixed(2)}</span>
    </div>`;

    billBreakdownContent.innerHTML = breakdownHtml;
    billBreakdown.style.display = 'block';
}

// Global variable for Vanta effect
let vantaEffect = window.vantaEffect || null;

// Initialize everything when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('=== Dashboard Loading ===');

    // Vanta background already initialized inline, no need to call again
    // Just ensure we have the reference
    if (window.vantaEffect) {
        vantaEffect = window.vantaEffect;
    }

    // Loader is shown by default in HTML, will be hidden after initialization
    initApp();
});

// Fetch upload mode setting from server
async function loadUploadMode() {
    try {
        const response = await fetch('/api/settings/upload-mode');
        if (response.ok) {
            const data = await response.json();
            uploadMode = data.upload_mode || 'sequential';
            console.log(`✓ Upload mode set to: ${uploadMode}`);
        } else {
            console.warn('Failed to fetch upload mode, defaulting to sequential');
            uploadMode = 'sequential';
        }
    } catch (error) {
        console.error('Error fetching upload mode:', error);
        uploadMode = 'sequential'; // Safe fallback
    }
}

// Main initialization function
async function initApp() {
    try {
        // 0. Load upload mode configuration (MUST complete first)
        await loadUploadMode();

        // 1. Setup navigation
        setupNavigation();

        // 2. Setup sidebar toggle
        setupSidebarToggle();

        // 3. Setup widgets toggle and load initial widget data
        setupWidgetsToggle();
        loadSidebarWidgets();

        // 4. Setup form buttons
        setupFormButtons();

        // 5. Load initial data
        loadCategories();
        loadPaymentMethods();
        populateDateSelectors();

        // 6. Initialize charts
        initCharts();

        // 7. Load user's preferred default page (or fallback to transactions)
        loadUserPreferredPage();

        console.log('✓ Dashboard loaded successfully');
    } catch (error) {
        console.error('✗ Dashboard initialization failed:', error);
        hideLoader(); // Hide loader even on error
    }
}

// Initialize Vanta.js background animation
function initVantaBackground() {
    // Skip if already initialized
    if (vantaEffect) {
        console.log('Vanta effect already initialized');
        return;
    }

    if (typeof VANTA !== 'undefined' && typeof VANTA.BIRDS !== 'undefined') {
        const loader = document.getElementById('pageLoader');
        if (loader) {
            const theme = document.documentElement.getAttribute('data-theme') || 'dark';
            const colors = theme === 'dark' ? {
                backgroundColor: 0x1a1a1a,
                color1: 0x007acc,
                color2: 0x0066ff,
                colorMode: 'variance'
            } : {
                backgroundColor: 0xf8fafc,
                color1: 0x0866ff,
                color2: 0x4299e1,
                colorMode: 'variance'
            };
            vantaEffect = VANTA.BIRDS({
                el: loader,
                mouseControls: true,
                touchControls: true,
                gyroControls: false,
                minHeight: 200.00,
                minWidth: 200.00,
                scale: 0.50,
                scaleMobile: 0.50,
                ...colors,
                quantity: 8.00,
                speedLimit: 4.00,
                separation: 50.00,
                alignment: 50.00,
                cohesion: 50.00
            });
            window.vantaEffect = vantaEffect;
        }
    }
}

// Hide the page loader
function hideLoader() {
    const loader = document.getElementById('pageLoader');
    const dashboardContent = document.getElementById('dashboardContent');

    if (loader) {
        loader.classList.add('fade-out');
        // Destroy Vanta effect
        if (vantaEffect) {
            vantaEffect.destroy();
            vantaEffect = null;
            window.vantaEffect = null;
        }
        // Show dashboard content
        if (dashboardContent) {
            dashboardContent.style.display = 'block';
        }
        // Remove from DOM after animation completes
        setTimeout(() => {
            loader.style.display = 'none';
        }, 500);
    }
}

// Show the page loader (for manual refresh)
function showLoader() {
    const loader = document.getElementById('pageLoader');
    const dashboardContent = document.getElementById('dashboardContent');

    if (loader) {
        // Hide dashboard content
        if (dashboardContent) {
            dashboardContent.style.display = 'none';
        }
        loader.style.display = 'flex';
        loader.classList.remove('fade-out');
        // Reinitialize Vanta effect if not already present
        if (!vantaEffect) {
            initVantaBackground();
        }
    }
}

// Load user's preferred default page
async function loadUserPreferredPage() {
    try {
        // Check for page parameter in URL first
        const urlParams = new URLSearchParams(window.location.search);
        const pageParam = urlParams.get('page');

        if (pageParam) {
            // Navigate to the specified page from URL parameter
            console.log('✓ Loading page from URL parameter:', pageParam);
            navigateToPage(pageParam);
            // Clear the URL parameter for cleaner URL
            window.history.replaceState({}, '', window.location.pathname);
            setTimeout(hideLoader, 800);
            return;
        }

        // Otherwise, load user's preferred page
        const response = await fetch('/api/user-preferences');
        if (response.ok) {
            const data = await response.json();
            const defaultPage = data.default_page || 'transactions';
            console.log('✓ Loading user preferred page:', defaultPage);
            navigateToPage(defaultPage);
            // Hide loader after navigation and a brief moment for data to load
            setTimeout(hideLoader, 800);
        } else {
            console.warn('Failed to fetch user preferences, loading default page');
            navigateToPage('transactions');
            setTimeout(hideLoader, 800);
        }
    } catch (error) {
        console.error('Error fetching user preferences:', error);
        navigateToPage('transactions');
        setTimeout(hideLoader, 800);
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
            const pageName = this.getAttribute('data-page');
            if (!pageName) return; // Allow normal navigation for real links
            e.preventDefault();
            navigateToPage(pageName);
        });
    });

    // Setup refresh button - recalculate balances and reload
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', recalculateAndRefresh);
    }
}

// ================================
// SIDEBAR TOGGLE
// ================================

function setupSidebarToggle() {
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('mainContent');
    const toggleBtn = document.getElementById('sidebarToggle');
    const expandTab = document.getElementById('sidebarExpandTab');
    const containerRow = document.querySelector('.container-fluid > .row');
    const mobileSidebarToggle = document.getElementById('mobileSidebarToggle');
    const sidebarOverlay = document.getElementById('sidebarOverlay');

    if (!sidebar || !mainContent || !toggleBtn || !expandTab) {
        console.warn('Sidebar toggle elements not found');
        return;
    }

    // Check localStorage for saved state (desktop only)
    const sidebarCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
    if (sidebarCollapsed) {
        sidebar.classList.add('collapsed');
        mainContent.classList.add('expanded');
        if (containerRow) containerRow.classList.add('sidebar-collapsed');
        expandTab.style.display = 'block';
    }

    // Toggle button click (collapse sidebar - desktop)
    toggleBtn.addEventListener('click', function() {
        sidebar.classList.add('collapsed');
        mainContent.classList.add('expanded');
        if (containerRow) containerRow.classList.add('sidebar-collapsed');
        expandTab.style.display = 'block';
        localStorage.setItem('sidebarCollapsed', 'true');
    });

    // Expand tab click (expand sidebar - desktop)
    expandTab.addEventListener('click', function() {
        sidebar.classList.remove('collapsed');
        mainContent.classList.remove('expanded');
        if (containerRow) containerRow.classList.remove('sidebar-collapsed');
        expandTab.style.display = 'none';
        localStorage.setItem('sidebarCollapsed', 'false');
    });

    // Mobile menu toggle
    if (mobileSidebarToggle && sidebarOverlay) {
        // Toggle button click (mobile)
        mobileSidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('show');
            sidebarOverlay.classList.toggle('show');

            // Change button text
            const icon = this.querySelector('i');
            if (sidebar.classList.contains('show')) {
                icon.className = 'fas fa-times';
            } else {
                icon.className = 'fas fa-bars';
            }
        });

        // Overlay click (close sidebar on mobile)
        sidebarOverlay.addEventListener('click', function() {
            sidebar.classList.remove('show');
            sidebarOverlay.classList.remove('show');
            const icon = mobileSidebarToggle.querySelector('i');
            icon.className = 'fas fa-bars';
        });

        // Close sidebar when clicking a nav link on mobile
        const navLinks = sidebar.querySelectorAll('.nav-link');
        navLinks.forEach(link => {
            link.addEventListener('click', function() {
                if (window.innerWidth < 768) {
                    sidebar.classList.remove('show');
                    sidebarOverlay.classList.remove('show');
                    const icon = mobileSidebarToggle.querySelector('i');
                    icon.className = 'fas fa-bars';
                }
            });
        });
    }

    console.log('✓ Sidebar toggle initialized');
}

function navigateToPage(pageName) {
    console.log('→ Navigating to:', pageName);

    // Get the page transition loader
    const transitionLoader = document.getElementById('pageTransitionLoader');

    // Show transition loader
    if (transitionLoader) {
        transitionLoader.classList.add('active');
    }

    // Small delay to ensure loader is visible before switching
    setTimeout(async () => {
        // Hide all pages
        const allPages = document.querySelectorAll('.page-content');
        allPages.forEach(page => {
            page.style.display = 'none';
            page.style.opacity = '0';
        });

        // Remove active from all nav links
        const allLinks = document.querySelectorAll('.sidebar .nav-link');
        allLinks.forEach(link => link.classList.remove('active'));

        // Show target page
        const targetPage = document.getElementById(pageName + 'Page');
        if (targetPage) {
            // Lazy-load HTML if page has data-lazy-url and hasn't been loaded yet
            const lazyUrl = targetPage.getAttribute('data-lazy-url');
            if (lazyUrl && !targetPage.hasAttribute('data-loaded')) {
                try {
                    console.log('⏳ Lazy loading:', pageName);
                    const resp = await fetch(lazyUrl);
                    if (resp.ok) {
                        targetPage.innerHTML = await resp.text();
                        targetPage.setAttribute('data-loaded', 'true');
                        console.log('✓ Lazy loaded:', pageName);
                    } else {
                        console.error('✗ Failed to load page:', resp.status);
                        targetPage.innerHTML = '<div class="alert alert-danger m-3"><i class="fas fa-exclamation-triangle me-2"></i>Failed to load page content. Please refresh.</div>';
                    }
                } catch (err) {
                    console.error('✗ Error loading page:', err);
                    targetPage.innerHTML = '<div class="alert alert-danger m-3"><i class="fas fa-exclamation-triangle me-2"></i>Failed to load page content. Please refresh.</div>';
                }
            }

            targetPage.style.display = 'block';
            console.log('✓ Showing:', pageName + 'Page');

            // Fade in the page
            setTimeout(() => {
                targetPage.style.transition = 'opacity 0.3s ease-in-out';
                targetPage.style.opacity = '1';
            }, 50);
        } else {
            console.error('✗ Page not found:', pageName + 'Page');
            if (transitionLoader) {
                transitionLoader.classList.remove('active');
            }
            return;
        }

        // Set active nav link
        const activeLink = document.querySelector(`[data-page="${pageName}"]`);
        if (activeLink) {
            activeLink.classList.add('active');
        }

        // Load page-specific data
        loadPageData(pageName);

        // Hide transition loader after content is ready
        setTimeout(() => {
            if (transitionLoader) {
                transitionLoader.classList.add('fade-out');
                setTimeout(() => {
                    transitionLoader.classList.remove('active', 'fade-out');
                }, 150);
            }
        }, 300);
    }, 50);
}

function loadPageData(pageName) {
    switch(pageName) {
        case 'transactions':
            loadTransactions();
            break;
        case 'reports':
            loadReports();
            break;
case 'tax':
            loadTaxCalculator();
            break;
        case 'rateTrends':
            if (typeof loadRateTrends === 'function') loadRateTrends();
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

    // Show/hide paid_at field when payment method changes
    const transPaymentMethod = document.getElementById('transPaymentMethod');
    const paidAtGroup = document.getElementById('paidAtGroup');
    const paidAtPaid = document.getElementById('paidAtPaid');
    const paidAtNotPaid = document.getElementById('paidAtNotPaid');

    if (transPaymentMethod && paidAtGroup) {
        transPaymentMethod.addEventListener('change', function() {
            if (this.value) {
                // Payment method selected - show payment status options
                paidAtGroup.style.display = 'block';
                // Default to "Paid"
                if (paidAtPaid) paidAtPaid.checked = true;
            } else {
                // No payment method - hide payment status
                paidAtGroup.style.display = 'none';
            }
        });
    }

    // Reset bill data when transaction modal is closed/cancelled
    const transactionModal = document.getElementById('transactionModal');
    if (transactionModal) {
        transactionModal.addEventListener('hidden.bs.modal', function() {
            // Clear captured bill data when modal is dismissed
            scannedBillContent = null;
            capturedBillImages = [];

            // Hide scan status if visible
            const scanStatus = document.getElementById('scanStatus');
            if (scanStatus) {
                scanStatus.style.display = 'none';
                scanStatus.style.color = '#ffc107';
            }

            // Hide bill breakdown if visible
            const billBreakdown = document.getElementById('billBreakdown');
            if (billBreakdown) {
                billBreakdown.style.display = 'none';
            }

            // Reset the form and modal title for next use
            document.getElementById('transactionForm').reset();
            document.getElementById('editTransactionId').value = '';
            document.querySelector('#transactionModal .modal-title').textContent = 'Add Transaction';

            // Reset payment method dropdown to "None"
            const paymentMethodSelect = document.getElementById('transPaymentMethod');
            if (paymentMethodSelect) {
                paymentMethodSelect.value = '';
            }

            // Hide and reset payment status field
            const paidAtGroup = document.getElementById('paidAtGroup');
            const paidAtPaid = document.getElementById('paidAtPaid');

            if (paidAtGroup) {
                paidAtGroup.style.display = 'none';
            }
            if (paidAtPaid) {
                paidAtPaid.checked = true;
            }
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

    // Preview filters button
    const previewFiltersBtn = document.getElementById('previewFiltersBtn');
    if (previewFiltersBtn) {
        previewFiltersBtn.addEventListener('click', previewFilterResults);
    }

    // Save current preset button
    const saveCurrentPresetBtn = document.getElementById('saveCurrentPresetBtn');
    if (saveCurrentPresetBtn) {
        saveCurrentPresetBtn.addEventListener('click', saveCurrentPreset);
    }

    // Setup filter modal to populate checkboxes when shown
    const filterModal = document.getElementById('filterModal');
    if (filterModal) {
        filterModal.addEventListener('shown.bs.modal', function() {
            // Only populate dropdowns and setup listeners once
            if (!filterDropdownsInitialized) {
                populateFilterDropdowns();
            }
            if (!filterSearchListenersInitialized) {
                setupFilterSearchListeners();
            }
            // These can be updated each time (lightweight operations)
            displaySavedPresets();
            displayRecentFilters();
            updateFilterPreview();
        });
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

    // View attachment button
    const viewAttachmentBtn = document.getElementById('viewAttachmentBtn');
    if (viewAttachmentBtn) {
        viewAttachmentBtn.addEventListener('click', loadAndDisplayAttachment);
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

    // If categories are already loaded, use cached data
    if (currentCategories && currentCategories.length > 0) {
        displayCategoriesInManagement(currentCategories, incomeList, expenseList);
        return;
    }

    // Show loading state only if we need to fetch
    incomeList.innerHTML = '<div class="text-center p-3"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';
    expenseList.innerHTML = '<div class="text-center p-3"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';

    fetch('/api/categories')
        .then(response => response.json())
        .then(categories => {
            currentCategories = categories; // Cache the categories
            displayCategoriesInManagement(categories, incomeList, expenseList);
        })
        .catch(error => {
            console.error('Error loading categories:', error);
            incomeList.innerHTML = '<div class="alert alert-danger">Failed to load categories</div>';
            expenseList.innerHTML = '<div class="alert alert-danger">Failed to load categories</div>';
        });
}

// Helper function to display categories in management modal
function displayCategoriesInManagement(categories, incomeList, expenseList) {
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

// ==================================================
// SIDEBAR WIDGETS
// ==================================================

/**
 * Setup widgets toggle functionality
 */
function setupWidgetsToggle() {
    const toggleBtn = document.getElementById('widgetsToggle');
    const widgetsContent = document.getElementById('widgetsContent');

    if (!toggleBtn || !widgetsContent) return;

    // Check localStorage for saved state
    const isCollapsed = localStorage.getItem('widgetsCollapsed') === 'true';

    if (isCollapsed) {
        widgetsContent.classList.add('collapsed');
        toggleBtn.classList.add('collapsed');
    }

    toggleBtn.addEventListener('click', function() {
        const isCurrentlyCollapsed = widgetsContent.classList.contains('collapsed');

        if (isCurrentlyCollapsed) {
            widgetsContent.classList.remove('collapsed');
            toggleBtn.classList.remove('collapsed');
            localStorage.setItem('widgetsCollapsed', 'false');
        } else {
            widgetsContent.classList.add('collapsed');
            toggleBtn.classList.add('collapsed');
            localStorage.setItem('widgetsCollapsed', 'true');
        }
    });
}

/**
 * Load sidebar widget data from the /api/sidebar-summary endpoint
 * and populate all widgets
 */
async function loadSidebarWidgets() {
    try {
        const response = await fetch('/api/sidebar-summary');
        if (!response.ok) {
            console.error('Failed to load sidebar widgets:', response.status);
            return;
        }

        const data = await response.json();
        console.log('Sidebar widgets data:', data);

        // Update balance widget
        const balanceElement = document.getElementById('widgetBalance');
        if (balanceElement && data.month_summary) {
            const balance = data.month_summary.balance || 0;
            const balanceText = balance >= 0 ?
                `+LKR ${balance.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}` :
                `LKR ${balance.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
            balanceElement.textContent = balanceText;
        }

        // Update exchange rate widget
        const rateElement = document.getElementById('widgetRate');
        const rateLabelElement = document.getElementById('widgetRateLabel');
        if (rateElement && data.exchange_rate) {
            const rate = data.exchange_rate.buy_rate || 0;
            const trend = data.exchange_rate.trend || '—';
            const bank = data.exchange_rate.bank || '';

            // Update label with bank name
            if (rateLabelElement && bank) {
                rateLabelElement.textContent = `USD→LKR (${bank})`;
            }

            // Update value with rate and trend
            rateElement.innerHTML = `${rate.toFixed(2)} <small style="margin-left:0.25rem;">${trend}</small>`;
        } else if (rateElement) {
            rateElement.textContent = '—';
            if (rateLabelElement) {
                rateLabelElement.textContent = 'USD→LKR';
            }
        }

        // Update unpaid widget
        const unpaidElement = document.getElementById('widgetUnpaid');
        const unpaidTile = document.getElementById('widgetUnpaidTile');
        if (unpaidElement && unpaidTile && data.month_summary) {
            const unpaidCount = data.month_summary.unpaid_count || 0;
            if (unpaidCount > 0) {
                unpaidElement.textContent = `${unpaidCount} transaction${unpaidCount !== 1 ? 's' : ''}`;
                unpaidTile.style.display = 'flex';
            } else {
                unpaidTile.style.display = 'none';
            }
        }

        // Update monthly tax payment widget
        const taxElement = document.getElementById('widgetTax');
        const taxLabel = document.getElementById('widgetTaxLabel');
        const taxTile = document.getElementById('widgetTaxTile');
        if (taxElement && taxTile && data.tax_summary) {
            const quarterlyPayment = data.tax_summary.quarterly_payment || 0;
            const assessmentYear = data.tax_summary.assessment_year || '';
            const currentQuarter = data.tax_summary.current_quarter || 1;

            // Update label with assessment year and quarter
            if (taxLabel && assessmentYear) {
                taxLabel.textContent = `Tax Q${currentQuarter} (${assessmentYear})`;
            }

            // Update value with quarterly payment
            taxElement.textContent = `LKR ${quarterlyPayment.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
            taxTile.style.display = 'flex';
        } else if (taxTile) {
            taxTile.style.display = 'none';
        }

    } catch (error) {
        console.error('Error loading sidebar widgets:', error);
    }
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

            // Update sidebar widgets
            loadSidebarWidgets();
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

    // Transactions come from backend sorted by display_order (ASC)
    // Calculate balance from BOTTOM to TOP so top row shows final cumulative balance

    // Reverse to calculate from bottom to top (last display_order first)
    const reversedForCalc = [...transactions].reverse();
    let runningBalance = 0;
    reversedForCalc.forEach(t => {
        const debit = parseFloat(t.debit) || 0;
        const credit = parseFloat(t.credit) || 0;
        runningBalance += debit - credit;
        t.calculatedBalance = runningBalance;
    });

    // Display transactions in the order they came from backend (by display_order)
    transactions.forEach(t => {
        const row = document.createElement('tr');

        // Check if transaction has payment method (handle both boolean and numeric values)
        const isDone = t.is_done === true || t.is_done === 1;
        const hasPaymentMethod = t.payment_method_id && t.payment_method_id !== null;

        // Store transaction data
        row.dataset.transaction = JSON.stringify(t);

        // Apply highlighting class if has payment method
        let rowClass = '';
        if (hasPaymentMethod && t.payment_method_color) {
            rowClass = `class="transaction-highlighted"`;
            row.dataset.paymentColor = t.payment_method_color;
        }

        // Format paid_at date if exists
        const paidAtDisplay = t.paid_at ? formatDate(t.paid_at) : '-';

        row.innerHTML = `
            <td class="text-center drag-handle" style="padding: 0.5rem; width: 40px; cursor: move;" title="Drag to reorder">
                <i class="fas fa-grip-vertical" style="font-size: 0.9rem; color: #999;"></i>
            </td>
            <td class="description-cell" style="cursor: pointer;" data-transaction-id="${t.id}">${t.description}</td>
            <td><span class="badge bg-secondary">${t.category_name || 'Uncategorized'}</span></td>
            <td class="text-success">${t.debit ? parseFloat(t.debit).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,') : '-'}</td>
            <td class="text-danger">${t.credit ? parseFloat(t.credit).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,') : '-'}</td>
            <td class="fw-bold">${parseFloat(t.calculatedBalance).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')}</td>
            <td class="small">${paidAtDisplay}</td>
            <td>${t.notes || '-'}</td>
            <td class="p-1">
                <div class="action-btn-group">
                    <button class="btn btn-sm btn-primary action-btn" onclick="editTransaction(${t.id})" title="Edit">
                        <i class="fas fa-edit" style="color: white;"></i>
                    </button>
                    <button class="btn btn-sm btn-danger action-btn" onclick="deleteTransaction(${t.id})" title="Delete">
                        <i class="fas fa-trash" style="color: white;"></i>
                    </button>
                    <button class="btn btn-sm btn-warning action-btn" onclick="showMoveCopyModal(${t.id}, 'move')" title="Move to Month">
                        <i class="fas fa-arrow-right" style="color: #000;"></i>
                    </button>
                    <button class="btn btn-sm btn-success action-btn" onclick="showMoveCopyModal(${t.id}, 'copy')" title="Copy to Month">
                        <i class="fas fa-copy" style="color: white;"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary action-btn" onclick="showBillContent(${t.id})" title="${t.bill_content ? 'View Bill' : 'No Bill Available'}" ${t.bill_content ? '' : 'disabled'}>
                        <i class="fas fa-receipt" style="color: white;"></i>
                    </button>
                    <button class="btn btn-sm btn-info action-btn" onclick="showAuditModal(${t.id})" title="Audit Log">
                        <i class="fas fa-history" style="color: #000;"></i>
                    </button>
                </div>
            </td>
        `;

        // Check if transaction is paid (handle both boolean and numeric values)
        const isPaid = t.is_paid === true || t.is_paid === 1;

        // Apply background color to all cells for proper highlighting
        if (hasPaymentMethod && t.payment_method_color) {
            row.classList.add('transaction-highlighted');
            const cells = row.querySelectorAll('td');
            cells.forEach((cell, index) => {
                // Apply to all cells except drag handle (index 0) and description (index 1)
                if (index !== 0 && index !== 1) {
                    cell.style.backgroundColor = t.payment_method_color;
                } else if (index === 1) {
                    // Apply to description cell only if is_paid is true
                    if (isPaid) {
                        cell.style.backgroundColor = t.payment_method_color;
                    }
                }
            });
        }

        // Add click handler on description cell to toggle paid status
        const descCell = row.querySelector('.description-cell');
        if (descCell) {
            descCell.dataset.isPaid = isPaid ? '1' : '0';
            descCell.addEventListener('click', function() {
                const transId = parseInt(this.dataset.transactionId);
                const cellIsPaid = this.dataset.isPaid === '1';

                if (cellIsPaid) {
                    showConfirmModal(
                        'Mark as Unpaid',
                        'Remove payment method from this transaction?',
                        function() {
                            markTransactionAsUnpaid(transId);
                        },
                        'Mark Unpaid',
                        'btn-warning'
                    );
                } else {
                    showPaymentMethodModal(transId, true);
                }
            });
        }

        // Store transaction data
        row.dataset.transactionId = t.id;
        row.dataset.displayOrder = t.display_order;

        // Add drag event listeners
        const dragHandle = row.querySelector('.drag-handle');

        // Only make row draggable when drag handle is pressed
        dragHandle.addEventListener('mousedown', function(e) {
            row.setAttribute('draggable', 'true');
        });

        dragHandle.addEventListener('mouseup', function(e) {
            row.setAttribute('draggable', 'false');
        });

        row.addEventListener('dragstart', function(e) {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', this.dataset.transactionId);
            this.classList.add('dragging');
            this.style.opacity = '0.5';
            dragHandle.style.cursor = 'grabbing';
        });

        row.addEventListener('dragend', function(e) {
            this.classList.remove('dragging');
            this.style.opacity = '1';
            this.setAttribute('draggable', 'false');
            dragHandle.style.cursor = 'grab';
        });

        row.addEventListener('dragover', function(e) {
            e.preventDefault();
            const draggingRow = document.querySelector('.dragging');
            if (draggingRow && draggingRow !== this) {
                const tbody = this.parentNode;
                const allRows = [...tbody.querySelectorAll('tr')];
                const draggingIndex = allRows.indexOf(draggingRow);
                const targetIndex = allRows.indexOf(this);

                if (draggingIndex < targetIndex) {
                    tbody.insertBefore(draggingRow, this.nextSibling);
                } else {
                    tbody.insertBefore(draggingRow, this);
                }
            }
        });

        row.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();

            const draggingRow = document.querySelector('.dragging');
            if (draggingRow) {
                // Get all rows in new order
                const tbody = this.parentNode;
                const allRows = [...tbody.querySelectorAll('tr')];

                // Build array of transaction IDs in new order
                const newOrder = allRows.map(r => parseInt(r.dataset.transactionId)).filter(id => !isNaN(id));

                // Send update to backend
                updateTransactionOrder(newOrder);
            }
        });

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

    // Filter out payment methods with zero net amount
    const filteredTotals = totals.filter(t => (t.net_amount || 0) !== 0);

    if (filteredTotals.length === 0) {
        container.innerHTML = '<div class="alert alert-info">All payment methods have zero net amounts.</div>';
        return;
    }

    let totalDebit = 0;
    let totalCredit = 0;

    const html = `
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th class="text-start" style="padding-left: 40px;">Payment Method</th>
                        <th class="text-start">Type</th>
                        <th class="text-center">Transactions</th>
                        <th class="text-end">Total Debit</th>
                        <th class="text-end">Total Credit</th>
                        <th class="text-end">Net Amount</th>
                    </tr>
                </thead>
                <tbody>
                    ${filteredTotals.map(t => {
                        const debit = t.total_debit || 0;
                        const credit = t.total_credit || 0;
                        const net = t.net_amount || 0;
                        totalDebit += debit;
                        totalCredit += credit;

                        return `
                            <tr>
                                <td class="text-start" style="vertical-align: middle;">
                                    <span class="payment-method-color-indicator" style="background-color: ${t.color}; vertical-align: middle;"></span>
                                    <strong>${t.name}</strong>
                                </td>
                                <td class="text-start" style="vertical-align: middle;">
                                    <span class="badge ${t.type === 'cash' ? 'bg-success' : 'bg-info'}">
                                        ${t.type === 'cash' ? 'Cash' : 'Credit Card'}
                                    </span>
                                </td>
                                <td class="text-center" style="vertical-align: middle;">${t.transaction_count || 0}</td>
                                <td class="text-end text-success" style="vertical-align: middle;">${parseFloat(debit).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')}</td>
                                <td class="text-end text-danger" style="vertical-align: middle;">${parseFloat(credit).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')}</td>
                                <td class="text-end fw-bold ${net >= 0 ? 'text-success' : 'text-danger'}" style="vertical-align: middle;">
                                    ${parseFloat(net).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')}
                                </td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
                <tfoot>
                    <tr class="table-active fw-bold">
                        <td class="text-start" colspan="3">TOTAL</td>
                        <td class="text-end text-success">${parseFloat(totalDebit).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')}</td>
                        <td class="text-end text-danger">${parseFloat(totalCredit).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')}</td>
                        <td class="text-end ${(totalDebit - totalCredit) >= 0 ? 'text-success' : 'text-danger'}">
                            ${parseFloat(totalDebit - totalCredit).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')}
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
    document.getElementById('transNotes').value = transaction.notes || '';

    // Set payment method (use payment_method_id if available)
    const paymentMethodSelect = document.getElementById('transPaymentMethod');
    if (paymentMethodSelect) {
        paymentMethodSelect.value = transaction.payment_method_id || '';
    }

    // Set payment status field if transaction has a payment method
    const paidAtGroup = document.getElementById('paidAtGroup');
    const paidAtPaid = document.getElementById('paidAtPaid');
    const paidAtNotPaid = document.getElementById('paidAtNotPaid');

    if (transaction.payment_method_id && paidAtGroup) {
        // Show payment status options
        paidAtGroup.style.display = 'block';

        // Check if transaction was marked as paid
        if (transaction.paid_at && paidAtPaid) {
            // Transaction is paid
            paidAtPaid.checked = true;
        } else if (paidAtNotPaid) {
            // Transaction is not paid
            paidAtNotPaid.checked = true;
        }
    } else if (paidAtGroup) {
        // No payment method, hide payment status
        paidAtGroup.style.display = 'none';
    }

    // Update modal title
    document.querySelector('#transactionModal .modal-title').textContent = 'Edit Transaction';

    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('transactionModal'));
    modal.show();
}

async function saveTransaction() {
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
        notes: document.getElementById('transNotes')?.value,
        payment_method_id: document.getElementById('transPaymentMethod')?.value || null,
        year: parseInt(year),
        month: parseInt(month)
    };

    // Handle payment status based on radio button selection
    if (data.payment_method_id) {
        const paidAtPaidRadio = document.getElementById('paidAtPaid');
        const paidAtNotPaidRadio = document.getElementById('paidAtNotPaid');

        if (paidAtPaidRadio && paidAtPaidRadio.checked) {
            // Mark as paid with current Sri Lankan time (UTC+5:30)
            data.is_paid = true;
            const now = new Date();
            const sriLankaTime = new Date(now.getTime() + (5.5 * 60 * 60 * 1000));
            data.paid_at = sriLankaTime.toISOString();
        } else if (paidAtNotPaidRadio && paidAtNotPaidRadio.checked) {
            // Mark as not paid (payment method selected but not paid yet)
            data.is_paid = false;
            data.paid_at = null;
        }
    }

    // Include scanned bill content if available
    if (scannedBillContent && !isEdit) {
        data.bill_content = JSON.stringify(scannedBillContent);
    }

    const url = isEdit ? `/api/transactions/${editId}` : '/api/transactions';
    const method = isEdit ? 'PUT' : 'POST';

    showLoading();

    // Handle bill image uploads based on configured mode
    let requestBody, requestHeaders;

    console.log(`[Upload Mode Check] Current uploadMode: '${uploadMode}', Has images: ${!!(capturedBillImages && capturedBillImages.length)}, Is edit: ${isEdit}`);

    if (uploadMode === 'sequential' && capturedBillImages && capturedBillImages.length > 0 && !isEdit) {
        // SEQUENTIAL MODE: Upload images one-by-one, then send transaction with GUIDs
        let attachmentGuids = [];
        try {
            console.log(`[Sequential Mode] Uploading ${capturedBillImages.length} image(s)...`);

            for (let i = 0; i < capturedBillImages.length; i++) {
                const formData = new FormData();
                formData.append('bill_image', capturedBillImages[i], capturedBillImages[i].name || `image_${i + 1}.jpg`);

                console.log(`Uploading image ${i + 1}/${capturedBillImages.length}...`);
                const uploadResponse = await fetch('/api/upload-bill-attachment', {
                    method: 'POST',
                    body: formData
                });

                if (uploadResponse.status === 413) {
                    throw new Error(`Image ${i + 1} is too large. Please use a smaller image.`);
                }

                const uploadResult = await uploadResponse.json();

                if (!uploadResponse.ok || !uploadResult.success) {
                    throw new Error(uploadResult.error || `Failed to upload image ${i + 1}`);
                }

                console.log(`✓ Image ${i + 1} uploaded:`, uploadResult.attachment_guid);
                attachmentGuids.push(uploadResult.attachment_guid);
            }

            console.log(`All ${attachmentGuids.length} images uploaded successfully`);
            data.attachments = attachmentGuids.join(',');
        } catch (error) {
            hideLoading();
            console.error('Error uploading images:', error);
            showToast(error.message || 'Failed to upload images', 'danger');
            return;
        }

        // Send transaction with just the GUIDs (JSON)
        requestBody = JSON.stringify(data);
        requestHeaders = { 'Content-Type': 'application/json' };

    } else if (uploadMode === 'batch' && capturedBillImages && capturedBillImages.length > 0 && !isEdit) {
        // BATCH MODE: Send all images with transaction in one multipart request (legacy)
        console.log(`[Batch Mode] Uploading ${capturedBillImages.length} image(s) with transaction...`);
        const formData = new FormData();

        // Add all data fields
        Object.keys(data).forEach(key => {
            if (data[key] !== null && data[key] !== undefined && data[key] !== '') {
                formData.append(key, data[key]);
            }
        });

        // Add all bill images
        capturedBillImages.forEach((img, idx) => {
            formData.append('bill_images', img, img.name || `image_${idx + 1}.jpg`);
        });

        requestBody = formData;
        requestHeaders = {}; // Let browser set Content-Type with boundary

    } else {
        // No images or editing mode - send as JSON
        requestBody = JSON.stringify(data);
        requestHeaders = { 'Content-Type': 'application/json' };
    }

    fetch(url, {
        method: method,
        headers: requestHeaders,
        body: requestBody
    })
    .then(response => {
        // Get response as text first
        return response.text().then(text => {
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

            // Clear bill content and captured images
            scannedBillContent = null;
            capturedBillImages = [];

            loadTransactions();
            loadSidebarWidgets();
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
                    loadSidebarWidgets();
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
                <div class="audit-log-entry mb-3 p-3 border rounded" style="background-color: var(--bg-tertiary);">
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
                <div class="audit-log-entry mb-3 p-3 border rounded" style="background-color: var(--bg-tertiary);">
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
// BILL CONTENT VIEWER
// ================================

function showBillContent(transactionId) {
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

    // Parse bill content
    let billContent = null;
    try {
        if (typeof transaction.bill_content === 'string') {
            billContent = JSON.parse(transaction.bill_content);
        } else if (typeof transaction.bill_content === 'object') {
            billContent = transaction.bill_content;
        }
    } catch (e) {
        console.error('Error parsing bill content:', e);
    }

    // Display bill content
    const billContentDisplay = document.getElementById('billContentDisplay');

    if (!billContent || !billContent.items || billContent.items.length === 0) {
        billContentDisplay.innerHTML = `
            <div class="text-center py-4">
                <i class="fas fa-receipt fa-3x text-muted mb-3"></i>
                <p class="text-muted">No bill items available</p>
            </div>
        `;
    } else {
        // Create a nice bill display
        const itemCount = billContent.items.length;
        let html = `
            <div class="bill-content-wrapper">
                <div class="text-center mb-4 pb-3 border-bottom">
                    <h4 class="mb-0">${billContent.shop_name || transaction.description}</h4>
                    <div class="text-muted mt-2">
                        <i class="fas fa-shopping-basket me-1"></i>${itemCount} item${itemCount !== 1 ? 's' : ''}
                    </div>
                </div>

                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead class="table-light">
                            <tr>
                                <th>Item</th>
                                <th class="text-center">Qty</th>
                                <th class="text-end">Price</th>
                                <th class="text-end">Discount</th>
                                <th class="text-end">Total</th>
                            </tr>
                        </thead>
                        <tbody>
        `;

        let subtotal = 0;
        billContent.items.forEach(item => {
            const qty = parseFloat(item.quantity || 1);
            const price = parseFloat(item.price || 0);
            const discount = parseFloat(item.discount || 0);
            const total = (qty * price) - (qty * discount);
            subtotal += total;

            html += `
                <tr>
                    <td><strong>${item.name}</strong></td>
                    <td class="text-center">${qty}</td>
                    <td class="text-end">${price.toFixed(2)}</td>
                    <td class="text-end" style="color: ${discount > 0 ? '#28a745' : '#6c757d'};">${discount > 0 ? '-' + discount.toFixed(2) : '-'}</td>
                    <td class="text-end">${total.toFixed(2)}</td>
                </tr>
            `;
        });

        html += `
                        </tbody>
                        <tfoot class="table-light">
        `;

        // Display subtotal if available
        if (billContent.subtotal && parseFloat(billContent.subtotal) > 0) {
            html += `
                            <tr>
                                <td colspan="4" class="text-end">Subtotal:</td>
                                <td class="text-end">${parseFloat(billContent.subtotal).toFixed(2)}</td>
                            </tr>
            `;
        } else if (subtotal > 0) {
            html += `
                            <tr>
                                <td colspan="4" class="text-end">Subtotal:</td>
                                <td class="text-end">${subtotal.toFixed(2)}</td>
                            </tr>
            `;
        }

        // Display discounts if available
        if (billContent.discounts && Array.isArray(billContent.discounts) && billContent.discounts.length > 0) {
            billContent.discounts.forEach(discount => {
                const discountAmount = parseFloat(discount.amount || 0);
                html += `
                            <tr class="table-success">
                                <td colspan="4" class="text-end">
                                    <i class="fas fa-tag me-2"></i>${discount.description || 'Discount'}:
                                </td>
                                <td class="text-end text-success">-${discountAmount.toFixed(2)}</td>
                            </tr>
                `;
            });
        }

        // Display final total (use exact amount from bill, not calculated)
        const finalTotal = parseFloat(billContent.amount) || 0;
        html += `
                            <tr>
                                <td colspan="4" class="text-end"><strong>Final Total:</strong></td>
                                <td class="text-end"><strong>${finalTotal.toFixed(2)}</strong></td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
            </div>
        `;

        billContentDisplay.innerHTML = html;
    }

    // Handle attachment button visibility
    const viewAttachmentBtn = document.getElementById('viewAttachmentBtn');
    const billAttachmentContainer = document.getElementById('billAttachmentContainer');

    // Reset attachment container
    billAttachmentContainer.style.display = 'none';

    if (transaction.attachments) {
        // Show the "View Attachment" button
        viewAttachmentBtn.style.display = 'inline-block';
        viewAttachmentBtn.dataset.transactionId = transactionId;
        viewAttachmentBtn.dataset.attachmentGuid = transaction.attachments;
    } else {
        // Hide the "View Attachment" button
        viewAttachmentBtn.style.display = 'none';
    }

    // Show the modal
    const modal = new bootstrap.Modal(document.getElementById('billContentModal'));
    modal.show();
}

// ================================
// ATTACHMENT DISPLAY FUNCTION
// ================================

async function loadAndDisplayAttachment() {
    const viewAttachmentBtn = document.getElementById('viewAttachmentBtn');
    const billAttachmentContainer = document.getElementById('billAttachmentContainer');

    const transactionId = viewAttachmentBtn.dataset.transactionId;
    const attachmentGuid = viewAttachmentBtn.dataset.attachmentGuid;

    if (!transactionId || !attachmentGuid) {
        showToast('Attachment information not available', 'danger');
        return;
    }

    // Show loading state
    billAttachmentContainer.innerHTML = `
        <div class="text-center py-3">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="text-muted mt-2">Loading attachment...</p>
        </div>
    `;
    billAttachmentContainer.style.display = 'block';

    // Disable button while loading
    viewAttachmentBtn.disabled = true;

    try {
        const response = await fetch(`/api/transactions/${transactionId}/attachment`);

        if (!response.ok) {
            throw new Error(`Failed to load attachment: ${response.statusText}`);
        }

        const data = await response.json();

        // Handle new multi-attachment format
        if (data.attachments && Array.isArray(data.attachments) && data.attachments.length > 0) {
            const attachments = data.attachments; // Display in capture order (first captured first)
            const attachmentCount = attachments.length;

            // Build HTML for all attachments
            let allAttachmentsHtml = '';

            for (let i = 0; i < attachments.length; i++) {
                const attachment = attachments[i];
                const isPdf = attachment.mime_type === 'application/pdf' ||
                             (attachment.file_name && attachment.file_name.toLowerCase().endsWith('.pdf'));

                const attachmentNumber = attachmentCount > 1 ? ` ${i + 1}/${attachmentCount}` : '';

                let attachmentContent;
                if (isPdf) {
                    // For PDFs, provide download and new tab options
                    attachmentContent = `
                        <div class="attachment-item ${i > 0 ? 'mt-4' : ''}">
                            ${attachmentCount > 1 ? `<div class="badge bg-secondary mb-2">Image ${i + 1}</div>` : ''}
                            <div class="alert alert-info mb-3">
                                <i class="fas fa-file-pdf me-2"></i>
                                <strong>PDF Attachment${attachmentNumber}</strong>
                                <div class="small mt-1">${attachment.file_name || 'document.pdf'}</div>
                            </div>
                            <div class="d-flex gap-2 mb-3">
                                <a href="${attachment.download_url}" class="btn btn-primary" download>
                                    <i class="fas fa-download me-1"></i>Download PDF
                                </a>
                                <a href="${attachment.file_url}" class="btn btn-outline-secondary" target="_blank">
                                    <i class="fas fa-external-link-alt me-1"></i>Open in New Tab
                                </a>
                            </div>
                            <div id="pdfLoadingSpinner_${i}" class="text-center py-3">
                                <div class="spinner-border text-primary" role="status">
                                    <span class="visually-hidden">Loading PDF...</span>
                                </div>
                                <p class="text-muted mt-2">Loading PDF preview...</p>
                            </div>
                            <div style="width: 100%; height: 600px; overflow: auto; border: 1px solid #ddd; border-radius: 5px; background: #f5f5f5; display: none;" id="pdfIframeContainer_${i}">
                                <iframe src="${attachment.file_url}" width="100%" height="100%" frameborder="0" style="background: white;" onload="document.getElementById('pdfLoadingSpinner_${i}').style.display='none'; document.getElementById('pdfIframeContainer_${i}').style.display='block';">
                                    <p>PDF preview not available. <a href="${attachment.download_url}" download>Download PDF</a></p>
                                </iframe>
                            </div>
                        </div>
                    `;
                } else {
                    // Display image with loading state
                    attachmentContent = `
                        <div class="attachment-item ${i > 0 ? 'mt-4' : ''}">
                            ${attachmentCount > 1 ? `<div class="badge bg-secondary mb-2">Image ${i + 1}</div>` : ''}
                            <div id="imageLoadingSpinner_${i}" class="text-center py-3">
                                <div class="spinner-border text-primary" role="status">
                                    <span class="visually-hidden">Loading image...</span>
                                </div>
                                <p class="text-muted mt-2">Loading image${attachmentNumber}...</p>
                            </div>
                            <img src="${attachment.file_url}" alt="Bill Attachment${attachmentNumber}" class="img-fluid rounded shadow-sm" style="max-width: 100%; height: auto; display: none;" onload="this.style.display='block'; document.getElementById('imageLoadingSpinner_${i}').style.display='none';" onerror="this.style.display='none'; document.getElementById('imageLoadingSpinner_${i}').innerHTML='&lt;div class=&quot;alert alert-danger&quot;&gt;&lt;i class=&quot;fas fa-exclamation-triangle me-2&quot;&gt;&lt;/i&gt;Failed to load image&lt;/div&gt;';">
                        </div>
                    `;
                }

                allAttachmentsHtml += attachmentContent;
            }

            billAttachmentContainer.innerHTML = `
                <div class="attachment-display">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <h6 class="mb-0">Bill Attachment${attachmentCount > 1 ? 's' : ''} ${attachmentCount > 1 ? `(${attachmentCount})` : ''}</h6>
                        <button class="btn btn-sm btn-outline-secondary" onclick="hideAttachment()">
                            <i class="fas fa-times"></i> Hide
                        </button>
                    </div>
                    ${allAttachmentsHtml}
                </div>
            `;
        } else if (data.file_url) {
            // Backward compatibility: handle old single-attachment format
            const isPdf = data.mime_type === 'application/pdf' ||
                         (data.file_name && data.file_name.toLowerCase().endsWith('.pdf'));

            let attachmentContent;
            if (isPdf) {
                attachmentContent = `
                    <div class="alert alert-info mb-3">
                        <i class="fas fa-file-pdf me-2"></i>
                        <strong>PDF Attachment</strong>
                        <div class="small mt-1">${data.file_name || 'document.pdf'}</div>
                    </div>
                    <div class="d-flex gap-2 mb-3">
                        <a href="${data.download_url}" class="btn btn-primary" download>
                            <i class="fas fa-download me-1"></i>Download PDF
                        </a>
                        <a href="${data.file_url}" class="btn btn-outline-secondary" target="_blank">
                            <i class="fas fa-external-link-alt me-1"></i>Open in New Tab
                        </a>
                    </div>
                    <div id="pdfLoadingSpinner" class="text-center py-3">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Loading PDF...</span>
                        </div>
                        <p class="text-muted mt-2">Loading PDF preview...</p>
                    </div>
                    <div style="width: 100%; height: 600px; overflow: auto; border: 1px solid #ddd; border-radius: 5px; background: #f5f5f5; display: none;" id="pdfIframeContainer">
                        <iframe src="${data.file_url}" width="100%" height="100%" frameborder="0" style="background: white;" onload="document.getElementById('pdfLoadingSpinner').style.display='none'; document.getElementById('pdfIframeContainer').style.display='block';">
                            <p>PDF preview not available. <a href="${data.download_url}" download>Download PDF</a></p>
                        </iframe>
                    </div>
                `;
            } else {
                attachmentContent = `
                    <div id="imageLoadingSpinner" class="text-center py-3">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Loading image...</span>
                        </div>
                        <p class="text-muted mt-2">Loading image...</p>
                    </div>
                    <img src="${data.file_url}" alt="Bill Attachment" class="img-fluid rounded shadow-sm" style="max-width: 100%; height: auto; display: none;" onload="this.style.display='block'; document.getElementById('imageLoadingSpinner').style.display='none';" onerror="this.style.display='none'; document.getElementById('imageLoadingSpinner').innerHTML='&lt;div class=&quot;alert alert-danger&quot;&gt;&lt;i class=&quot;fas fa-exclamation-triangle me-2&quot;&gt;&lt;/i&gt;Failed to load image&lt;/div&gt;';">
                `;
            }

            billAttachmentContainer.innerHTML = `
                <div class="attachment-display">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <h6 class="mb-0">Bill Attachment</h6>
                        <button class="btn btn-sm btn-outline-secondary" onclick="hideAttachment()">
                            <i class="fas fa-times"></i> Hide
                        </button>
                    </div>
                    ${attachmentContent}
                </div>
            `;
        } else {
            throw new Error('No attachments returned from server');
        }
    } catch (error) {
        console.error('Error loading attachment:', error);
        billAttachmentContainer.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>
                Failed to load attachment: ${error.message}
            </div>
        `;
    } finally {
        // Re-enable button
        viewAttachmentBtn.disabled = false;
    }
}

function hideAttachment() {
    const billAttachmentContainer = document.getElementById('billAttachmentContainer');
    billAttachmentContainer.style.display = 'none';
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
        ? `<span class="text-success">Income: ${parseFloat(transaction.debit).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')}</span>`
        : `<span class="text-danger">Expense: ${parseFloat(transaction.credit).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')}</span>`;

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
        }
    })
    .catch(error => {
        hideLoading();
        console.error(`Error ${action}ing transaction:`, error);
        showToast(`Error ${action}ing transaction`, 'danger');
    });
}

// ================================
// DOWNLOAD/EXPORT TRANSACTIONS
// ================================

function downloadTransactions(format) {
    // Get current month/year
    const monthYear = document.getElementById('monthYearPicker').value;
    const [year, month] = monthYear.split('-').map(Number);

    // Build download URL with current filters
    const params = new URLSearchParams({
        year: year,
        month: month,
        format: format
    });

    // Add active filters if any
    const activeFilters = getActiveFilters();
    if (activeFilters) {
        Object.keys(activeFilters).forEach(key => {
            if (activeFilters[key]) {
                params.append(key, activeFilters[key]);
            }
        });
    }

    // Create download URL
    const downloadUrl = `/api/transactions/export?${params.toString()}`;

    // Close the modal
    const modal = bootstrap.Modal.getInstance(document.getElementById('downloadModal'));
    if (modal) modal.hide();

    // Show loading
    showLoading();

    // Trigger download
    fetch(downloadUrl)
        .then(response => {
            if (!response.ok) {
                throw new Error('Download failed');
            }
            return response.blob();
        })
        .then(blob => {
            hideLoading();

            // Create download link
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;

            // Set filename based on format
            const monthName = new Date(year, month - 1).toLocaleString('default', { month: 'long' });
            const extensions = { csv: 'csv', pdf: 'pdf', excel: 'xlsx' };
            a.download = `transactions_${monthName}_${year}.${extensions[format]}`;

            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            showToast(`Transactions downloaded as ${format.toUpperCase()}`, 'success');
        })
        .catch(error => {
            hideLoading();
            console.error('Download error:', error);
            showToast('Error downloading transactions', 'danger');
        });
}

function getActiveFilters() {
    // Return current filter state if filters are active
    // This should match the filter logic used in loadTransactions
    const filters = {};

    // Add filter extraction logic here if needed
    // For now, return empty to download all transactions for the month

    return filters;
}

// ================================
// TRANSACTION REORDERING
// ================================

function updateTransactionOrder(transactionIds) {
    showLoading();

    fetch('/api/transactions/reorder', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ transaction_ids: transactionIds })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showToast('Transaction order updated successfully', 'success');
            // Reload transactions to recalculate balances with a slight delay
            setTimeout(() => {
                loadTransactions();
            }, 500);
        } else {
            showToast(data.error || 'Failed to update transaction order', 'danger');
            // Reload to restore original order
            loadTransactions();
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error updating transaction order:', error);
        showToast('Error updating transaction order', 'danger');
        // Reload to restore original order
        loadTransactions();
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

        case 'yesterday':
            const yesterday = new Date(today);
            yesterday.setDate(yesterday.getDate() - 1);
            const yyyyY = yesterday.getFullYear();
            const mmY = String(yesterday.getMonth() + 1).padStart(2, '0');
            const ddY = String(yesterday.getDate()).padStart(2, '0');
            const yesterdayStr = `${yyyyY}-${mmY}-${ddY}`;
            document.getElementById('filterStartDate').value = yesterdayStr;
            document.getElementById('filterEndDate').value = yesterdayStr;
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

        case 'last30days':
            const last30days = new Date(today);
            last30days.setDate(last30days.getDate() - 30);
            const yyyy30 = last30days.getFullYear();
            const mm30 = String(last30days.getMonth() + 1).padStart(2, '0');
            const dd30 = String(last30days.getDate()).padStart(2, '0');
            document.getElementById('filterStartDate').value = `${yyyy30}-${mm30}-${dd30}`;
            document.getElementById('filterEndDate').value = todayStr;
            break;

        case 'thisMonth':
            const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
            const yyyyFirst = firstDay.getFullYear();
            const mmFirst = String(firstDay.getMonth() + 1).padStart(2, '0');
            document.getElementById('filterStartDate').value = `${yyyyFirst}-${mmFirst}-01`;
            document.getElementById('filterEndDate').value = todayStr;
            break;

        case 'lastMonth':
            const lastMonthDate = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            const lastMonthEnd = new Date(today.getFullYear(), today.getMonth(), 0);
            const yyyyLM = lastMonthDate.getFullYear();
            const mmLM = String(lastMonthDate.getMonth() + 1).padStart(2, '0');
            const yyyyLME = lastMonthEnd.getFullYear();
            const mmLME = String(lastMonthEnd.getMonth() + 1).padStart(2, '0');
            const ddLME = String(lastMonthEnd.getDate()).padStart(2, '0');
            document.getElementById('filterStartDate').value = `${yyyyLM}-${mmLM}-01`;
            document.getElementById('filterEndDate').value = `${yyyyLME}-${mmLME}-${ddLME}`;
            break;

        case 'thisQuarter':
            const currentQuarter = Math.floor(today.getMonth() / 3);
            const quarterStart = new Date(today.getFullYear(), currentQuarter * 3, 1);
            const yyyyQS = quarterStart.getFullYear();
            const mmQS = String(quarterStart.getMonth() + 1).padStart(2, '0');
            document.getElementById('filterStartDate').value = `${yyyyQS}-${mmQS}-01`;
            document.getElementById('filterEndDate').value = todayStr;
            break;

        case 'thisYear':
            document.getElementById('filterStartDate').value = `${yyyy}-01-01`;
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

        case 'paid':
            document.getElementById('filterStatusPaid').checked = true;
            break;

        case 'highValue':
            document.getElementById('filterMinAmount').value = '500';
            break;
    }

    // Apply the filters
    applyFilters();
}

// Select/Deselect All Functions
function selectAllCategories() {
    document.querySelectorAll('.filter-category-checkbox').forEach(cb => cb.checked = true);
    updateFilterPreview();
}

function deselectAllCategories() {
    document.querySelectorAll('.filter-category-checkbox').forEach(cb => cb.checked = false);
    updateFilterPreview();
}

function selectAllPaymentMethods() {
    document.querySelectorAll('.filter-payment-checkbox').forEach(cb => cb.checked = true);
    updateFilterPreview();
}

function deselectAllPaymentMethods() {
    document.querySelectorAll('.filter-payment-checkbox').forEach(cb => cb.checked = false);
    updateFilterPreview();
}

// New filter helper functions
function selectIncomeCategoriesOnly() {
    document.querySelectorAll('.filter-category-checkbox').forEach(cb => {
        const catId = parseInt(cb.value);
        const cat = currentCategories.find(c => c.id === catId);
        cb.checked = cat && cat.type === 'income';
    });
    updateFilterPreview();
}

function selectExpenseCategoriesOnly() {
    document.querySelectorAll('.filter-category-checkbox').forEach(cb => {
        const catId = parseInt(cb.value);
        const cat = currentCategories.find(c => c.id === catId);
        cb.checked = cat && cat.type === 'expense';
    });
    updateFilterPreview();
}

function selectCashPaymentMethodsOnly() {
    document.querySelectorAll('.filter-payment-checkbox').forEach(cb => {
        const methodId = parseInt(cb.value);
        const method = paymentMethods.find(m => m.id === methodId);
        cb.checked = method && method.type === 'cash';
    });
    updateFilterPreview();
}

function selectCardPaymentMethodsOnly() {
    document.querySelectorAll('.filter-payment-checkbox').forEach(cb => {
        const methodId = parseInt(cb.value);
        const method = paymentMethods.find(m => m.id === methodId);
        cb.checked = method && method.type === 'credit_card';
    });
    updateFilterPreview();
}

function setAmountRange(min, max) {
    document.getElementById('filterMinAmount').value = min || '';
    document.getElementById('filterMaxAmount').value = max || '';
    updateFilterPreview();
}

function applyFilters() {
    // Get filter values
    activeFilters.description = document.getElementById('filterDescription')?.value.trim() || '';
    activeFilters.notes = document.getElementById('filterNotes')?.value.trim() || '';
    activeFilters.caseSensitive = document.getElementById('filterCaseSensitive')?.checked || false;
    activeFilters.excludeWeekends = document.getElementById('filterExcludeWeekends')?.checked || false;

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

    // Save to recent filters
    saveToRecentFilters();

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
        notes: '',
        caseSensitive: false,
        excludeWeekends: false
    };

    // Clear form inputs
    const descInput = document.getElementById('filterDescription');
    const notesInput = document.getElementById('filterNotes');
    const minAmountInput = document.getElementById('filterMinAmount');
    const maxAmountInput = document.getElementById('filterMaxAmount');
    const startDateInput = document.getElementById('filterStartDate');
    const endDateInput = document.getElementById('filterEndDate');
    const caseSensitiveInput = document.getElementById('filterCaseSensitive');
    const excludeWeekendsInput = document.getElementById('filterExcludeWeekends');

    if (descInput) descInput.value = '';
    if (notesInput) notesInput.value = '';
    if (minAmountInput) minAmountInput.value = '';
    if (maxAmountInput) maxAmountInput.value = '';
    if (startDateInput) startDateInput.value = '';
    if (endDateInput) endDateInput.value = '';
    if (caseSensitiveInput) caseSensitiveInput.checked = false;
    if (excludeWeekendsInput) excludeWeekendsInput.checked = false;

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
    updateFilterPreview();
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
            amountText = `${parseFloat(activeFilters.minAmount).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')} - ${parseFloat(activeFilters.maxAmount).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')}`;
        } else if (activeFilters.minAmount !== null) {
            amountText = `≥ ${parseFloat(activeFilters.minAmount).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')}`;
        } else {
            amountText = `≤ ${parseFloat(activeFilters.maxAmount).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,')}`;
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

    // Always update in modal preview
    updateFilterPreviewDisplay();
}

// New filter functions for presets, recent, and search

function saveToRecentFilters() {
    // Create a snapshot of current filters
    const filterSnapshot = {
        timestamp: new Date().toISOString(),
        filters: JSON.parse(JSON.stringify(activeFilters))
    };

    // Add to beginning of array
    recentFilters.unshift(filterSnapshot);

    // Keep only last 5
    recentFilters = recentFilters.slice(0, 5);

    // Save to localStorage
    localStorage.setItem('recentFilters', JSON.stringify(recentFilters));

    // Update UI
    displayRecentFilters();
}

function displayRecentFilters() {
    const container = document.getElementById('recentFiltersContainer');
    if (!container) return;

    if (recentFilters.length === 0) {
        container.innerHTML = '<small class="text-muted">No recent filters</small>';
        return;
    }

    container.innerHTML = '';
    recentFilters.forEach((filterSnapshot, index) => {
        const filters = filterSnapshot.filters;
        const date = new Date(filterSnapshot.timestamp);
        const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        // Create short description
        let desc = [];
        if (filters.description) desc.push('Desc');
        if (filters.categories.length > 0) desc.push(`${filters.categories.length} Cat`);
        if (filters.types.length > 0) desc.push(filters.types.join('/'));
        if (filters.minAmount || filters.maxAmount) desc.push('Amount');
        if (filters.startDate || filters.endDate) desc.push('Date');

        const badge = document.createElement('span');
        badge.className = 'badge bg-info preset-badge';
        badge.innerHTML = `
            <i class="fas fa-history me-1"></i>
            ${desc.length > 0 ? desc.join(', ') : 'Filter'} (${timeStr})
        `;
        badge.style.cursor = 'pointer';
        badge.onclick = () => loadFilterFromSnapshot(filterSnapshot);
        container.appendChild(badge);
    });
}

function displaySavedPresets() {
    const container = document.getElementById('savedPresetsContainer');
    if (!container) return;

    if (savedFilterPresets.length === 0) {
        container.innerHTML = '<small class="text-muted">No saved presets yet</small>';
        return;
    }

    container.innerHTML = '';
    savedFilterPresets.forEach((preset, index) => {
        const badge = document.createElement('span');
        badge.className = 'badge bg-primary preset-badge';
        badge.innerHTML = `
            <i class="fas fa-bookmark me-1"></i>
            ${preset.name}
            <button class="btn-close btn-close-white" onclick="event.stopPropagation(); deletePreset(${index})"></button>
        `;
        badge.style.cursor = 'pointer';
        badge.onclick = () => loadFilterFromPreset(preset);
        container.appendChild(badge);
    });
}

function loadFilterFromSnapshot(snapshot) {
    const filters = snapshot.filters;
    loadFiltersIntoForm(filters);
    showToast('Recent filter loaded', 'info');
}

function loadFilterFromPreset(preset) {
    loadFiltersIntoForm(preset.filters);
    showToast(`Preset "${preset.name}" loaded`, 'success');
}

function loadFiltersIntoForm(filters) {
    // Clear first
    clearFiltersWithoutReload();

    // Load text inputs
    if (filters.description) document.getElementById('filterDescription').value = filters.description;
    if (filters.notes) document.getElementById('filterNotes').value = filters.notes;
    if (filters.caseSensitive) document.getElementById('filterCaseSensitive').checked = true;
    if (filters.excludeWeekends) document.getElementById('filterExcludeWeekends').checked = true;

    // Load categories
    filters.categories.forEach(catId => {
        const checkbox = document.querySelector(`.filter-category-checkbox[value="${catId}"]`);
        if (checkbox) checkbox.checked = true;
    });

    // Load payment methods
    filters.paymentMethods.forEach(methodId => {
        const checkbox = document.querySelector(`.filter-payment-checkbox[value="${methodId}"]`);
        if (checkbox) checkbox.checked = true;
    });

    // Load types
    filters.types.forEach(type => {
        const checkbox = document.querySelector(`.filter-type-checkbox[value="${type}"]`);
        if (checkbox) checkbox.checked = true;
    });

    // Load statuses
    filters.statuses.forEach(status => {
        const checkbox = document.querySelector(`.filter-status-checkbox[value="${status}"]`);
        if (checkbox) checkbox.checked = true;
    });

    // Load amounts
    if (filters.minAmount !== null) document.getElementById('filterMinAmount').value = filters.minAmount;
    if (filters.maxAmount !== null) document.getElementById('filterMaxAmount').value = filters.maxAmount;

    // Load dates
    if (filters.startDate) document.getElementById('filterStartDate').value = filters.startDate;
    if (filters.endDate) document.getElementById('filterEndDate').value = filters.endDate;

    updateFilterPreview();
}

function saveCurrentPreset() {
    const presetName = prompt('Enter a name for this filter preset:');
    if (!presetName || presetName.trim() === '') {
        showToast('Preset name is required', 'warning');
        return;
    }

    // Get current filter values from form
    const currentFilters = {
        description: document.getElementById('filterDescription')?.value.trim() || '',
        notes: document.getElementById('filterNotes')?.value.trim() || '',
        caseSensitive: document.getElementById('filterCaseSensitive')?.checked || false,
        excludeWeekends: document.getElementById('filterExcludeWeekends')?.checked || false,
        categories: Array.from(document.querySelectorAll('.filter-category-checkbox:checked')).map(cb => cb.value),
        paymentMethods: Array.from(document.querySelectorAll('.filter-payment-checkbox:checked')).map(cb => cb.value),
        types: Array.from(document.querySelectorAll('.filter-type-checkbox:checked')).map(cb => cb.value),
        statuses: Array.from(document.querySelectorAll('.filter-status-checkbox:checked')).map(cb => cb.value),
        minAmount: document.getElementById('filterMinAmount')?.value ? parseFloat(document.getElementById('filterMinAmount').value) : null,
        maxAmount: document.getElementById('filterMaxAmount')?.value ? parseFloat(document.getElementById('filterMaxAmount').value) : null,
        startDate: document.getElementById('filterStartDate')?.value || null,
        endDate: document.getElementById('filterEndDate')?.value || null
    };

    const preset = {
        name: presetName.trim(),
        filters: currentFilters,
        created: new Date().toISOString()
    };

    savedFilterPresets.push(preset);
    localStorage.setItem('filterPresets', JSON.stringify(savedFilterPresets));

    displaySavedPresets();
    showToast(`Preset "${presetName}" saved successfully`, 'success');
}

function deletePreset(index) {
    const preset = savedFilterPresets[index];
    if (confirm(`Delete preset "${preset.name}"?`)) {
        savedFilterPresets.splice(index, 1);
        localStorage.setItem('filterPresets', JSON.stringify(savedFilterPresets));
        displaySavedPresets();
        showToast('Preset deleted', 'info');
    }
}

// Filter preview functionality
let updateFilterPreviewTimeout = null;
function updateFilterPreview() {
    // Debounce the update to avoid blocking the UI on rapid input changes
    if (updateFilterPreviewTimeout) {
        clearTimeout(updateFilterPreviewTimeout);
    }
    updateFilterPreviewTimeout = setTimeout(() => {
        updateFilterPreviewDisplay();
    }, 100); // 100ms debounce
}

function updateFilterPreviewDisplay() {
    const listEl = document.getElementById('activeFiltersList');
    if (!listEl) return;

    // Collect current filter selections
    const desc = document.getElementById('filterDescription')?.value.trim() || '';
    const notes = document.getElementById('filterNotes')?.value.trim() || '';
    const categories = Array.from(document.querySelectorAll('.filter-category-checkbox:checked'));
    const paymentMethods = Array.from(document.querySelectorAll('.filter-payment-checkbox:checked'));
    const types = Array.from(document.querySelectorAll('.filter-type-checkbox:checked'));
    const statuses = Array.from(document.querySelectorAll('.filter-status-checkbox:checked'));
    const minAmount = document.getElementById('filterMinAmount')?.value;
    const maxAmount = document.getElementById('filterMaxAmount')?.value;
    const startDate = document.getElementById('filterStartDate')?.value;
    const endDate = document.getElementById('filterEndDate')?.value;

    listEl.innerHTML = '';
    let hasFilters = false;

    if (desc) {
        hasFilters = true;
        listEl.innerHTML += `<span class="badge bg-primary rounded-pill"><i class="fas fa-file-alt me-1"></i>Desc: "${desc}"</span>`;
    }
    if (notes) {
        hasFilters = true;
        listEl.innerHTML += `<span class="badge bg-primary rounded-pill"><i class="fas fa-sticky-note me-1"></i>Notes: "${notes}"</span>`;
    }
    if (categories.length > 0) {
        hasFilters = true;
        listEl.innerHTML += `<span class="badge bg-info text-dark rounded-pill"><i class="fas fa-tags me-1"></i>${categories.length} Categories</span>`;
    }
    if (paymentMethods.length > 0) {
        hasFilters = true;
        listEl.innerHTML += `<span class="badge bg-info text-dark rounded-pill"><i class="fas fa-credit-card me-1"></i>${paymentMethods.length} Payment Methods</span>`;
    }
    if (types.length > 0) {
        hasFilters = true;
        listEl.innerHTML += `<span class="badge bg-warning text-dark rounded-pill"><i class="fas fa-exchange-alt me-1"></i>${types.map(t => t.value).join('/')}</span>`;
    }
    if (statuses.length > 0) {
        hasFilters = true;
        listEl.innerHTML += `<span class="badge bg-success rounded-pill"><i class="fas fa-check-circle me-1"></i>${statuses.length} Statuses</span>`;
    }
    if (minAmount || maxAmount) {
        hasFilters = true;
        let amtText = '';
        if (minAmount && maxAmount) amtText = `$${minAmount} - $${maxAmount}`;
        else if (minAmount) amtText = `≥ $${minAmount}`;
        else amtText = `≤ $${maxAmount}`;
        listEl.innerHTML += `<span class="badge bg-secondary rounded-pill"><i class="fas fa-dollar-sign me-1"></i>${amtText}</span>`;
    }
    if (startDate || endDate) {
        hasFilters = true;
        let dateText = '';
        if (startDate && endDate) dateText = `${startDate} to ${endDate}`;
        else if (startDate) dateText = `From ${startDate}`;
        else dateText = `Until ${endDate}`;
        listEl.innerHTML += `<span class="badge bg-secondary rounded-pill"><i class="fas fa-calendar me-1"></i>${dateText}</span>`;
    }

    if (!hasFilters) {
        listEl.innerHTML = '<span class="badge bg-secondary">No filters applied</span>';
    }
}

function previewFilterResults() {
    // This would ideally make an API call to get count without actually applying filters
    // For now, just show a message
    showToast('Filter preview: Apply filters to see results', 'info');

    // Update the count badge (placeholder)
    const countBadge = document.getElementById('filterPreviewCount');
    if (countBadge) {
        countBadge.textContent = 'Preview not available';
    }
}

// Search within categories and payment methods
function setupFilterSearchListeners() {
    // Only initialize once to prevent duplicate event listeners
    if (filterSearchListenersInitialized) {
        return;
    }

    const categorySearch = document.getElementById('categorySearchInput');
    const paymentSearch = document.getElementById('paymentSearchInput');

    if (categorySearch) {
        categorySearch.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            document.querySelectorAll('#filterCategoryCheckboxes .form-check').forEach(checkDiv => {
                const label = checkDiv.querySelector('label');
                const text = label ? label.textContent.toLowerCase() : '';
                checkDiv.style.display = text.includes(searchTerm) ? 'block' : 'none';
            });
        });
    }

    if (paymentSearch) {
        paymentSearch.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            document.querySelectorAll('#filterPaymentMethodCheckboxes .form-check').forEach(checkDiv => {
                const label = checkDiv.querySelector('label');
                const text = label ? label.textContent.toLowerCase() : '';
                checkDiv.style.display = text.includes(searchTerm) ? 'block' : 'none';
            });
        });
    }

    // Add change listeners to all filter inputs for live preview
    const filterInputs = [
        'filterDescription', 'filterNotes', 'filterMinAmount', 'filterMaxAmount',
        'filterStartDate', 'filterEndDate', 'filterCaseSensitive', 'filterExcludeWeekends'
    ];
    filterInputs.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', updateFilterPreview);
            el.addEventListener('change', updateFilterPreview);
        }
    });

    // Add listeners to checkboxes
    document.addEventListener('change', function(e) {
        if (e.target.matches('.filter-category-checkbox, .filter-payment-checkbox, .filter-type-checkbox, .filter-status-checkbox')) {
            updateFilterPreview();
        }
    });

    filterSearchListenersInitialized = true;
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
        case 'paymentMethodReport':
            fetchPromise = loadPaymentMethodReport(year, month, rangeType);
            break;
        case 'spendingHeatmapReport':
            fetchPromise = loadSpendingHeatmapReport(year, month, rangeType);
            break;
        case 'yearOverYearReport':
            fetchPromise = loadYearOverYearReport();
            break;
        case 'incomeSourcesReport':
            fetchPromise = loadIncomeSourcesReport(year, month, rangeType);
            break;
        case 'transactionStatusReport':
            fetchPromise = loadTransactionStatusReport(year, month, rangeType);
            break;
        case 'expenseGrowthReport':
            fetchPromise = loadExpenseGrowthReport(year);
            break;
        case 'savingsRateReport':
            fetchPromise = loadSavingsRateReport(year, rangeType);
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

function loadPaymentMethodReport(year, month, rangeType) {
    return fetch(`/api/reports/payment-method-analysis?range=${rangeType}&year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => updatePaymentMethodChart(data));
}

function loadSpendingHeatmapReport(year, month, rangeType) {
    return fetch(`/api/reports/spending-heatmap?range=${rangeType}&year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => updateSpendingHeatmapChart(data));
}

function loadYearOverYearReport() {
    return fetch(`/api/reports/year-over-year`)
        .then(response => response.json())
        .then(data => updateYearOverYearChart(data));
}

function loadIncomeSourcesReport(year, month, rangeType) {
    return fetch(`/api/reports/income-sources?range=${rangeType}&year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => updateIncomeSourcesChart(data));
}

function loadTransactionStatusReport(year, month, rangeType) {
    return fetch(`/api/reports/transaction-status?range=${rangeType}&year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => updateTransactionStatusChart(data));
}

function loadExpenseGrowthReport(year) {
    return fetch(`/api/reports/expense-growth?year=${year}`)
        .then(response => response.json())
        .then(data => updateExpenseGrowthChart(data));
}

function loadSavingsRateReport(year, rangeType) {
    return fetch(`/api/reports/savings-rate?range=${rangeType}&year=${year}`)
        .then(response => response.json())
        .then(data => updateSavingsRateChart(data));
}

// ================================
// CHARTS
// ================================

function initCharts() {
    // Overview charts removed
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
                        callback: value => 'රු ' + value.toLocaleString()
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
                                return ctx.label + ': රු ' + ctx.parsed.toLocaleString() + ' (' + percentage + '%)';
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
                                return ctx.label + ': රු ' + ctx.parsed.toLocaleString() + ' (' + percentage + '%)';
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
                <td class="text-end">රු ${row.amount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
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
                <td class="text-end">රු ${row.amount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                <td class="text-end">${percentage}%</td>
            </tr>
        `;
    }).join('');

    // Update totals
    totalIncomeElement.textContent = `රු ${totalIncome.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    totalExpensesElement.textContent = `රු ${totalExpense.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
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
    netSavingsElement.textContent = `රු ${netSavings.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
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
                        callback: value => 'රු ' + value.toLocaleString()
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.dataset.label + ': රු ' + ctx.parsed.y.toLocaleString()
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
                        callback: value => 'රු ' + value.toLocaleString()
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
                        callback: value => 'රු ' + value.toLocaleString()
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.dataset.label + ': රු ' + ctx.parsed.y.toLocaleString()
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
                <td>රු ${(d.avg_monthly_spending || 0).toLocaleString()}</td>
                <td>රු ${(d.min_spending || 0).toLocaleString()}</td>
                <td>රු ${(d.max_spending || 0).toLocaleString()}</td>
                <td>රු ${(d.std_deviation || 0).toLocaleString()}</td>
            </tr>
        `).join('');
    }
}

function updatePaymentMethodChart(data) {
    const ctx = document.getElementById('paymentMethodChart');
    if (!ctx || !data) return;

    if (charts.paymentMethod) {
        charts.paymentMethod.destroy();
    }

    const labels = data.map(d => d.payment_method || 'No Payment Method');
    const expenses = data.map(d => d.total_expenses || 0);
    const colors = data.map(d => d.color || '#6c757d');

    charts.paymentMethod = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: expenses,
                backgroundColor: colors,
                borderWidth: 2,
                borderColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right'
                },
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.label + ': රු ' + ctx.parsed.toLocaleString()
                    }
                }
            }
        }
    });

    // Update table
    const tbody = document.getElementById('paymentMethodTableBody');
    if (tbody) {
        tbody.innerHTML = data.map(d => `
            <tr>
                <td><span class="badge" style="background-color: ${d.color || '#6c757d'}">${d.payment_method || 'None'}</span></td>
                <td class="text-end">රු ${(d.total_income || 0).toLocaleString()}</td>
                <td class="text-end">රු ${(d.total_expenses || 0).toLocaleString()}</td>
                <td class="text-end">${d.transaction_count || 0}</td>
                <td class="text-end">රු ${(d.avg_expense || 0).toLocaleString()}</td>
            </tr>
        `).join('');
    }
}

function updateSpendingHeatmapChart(data) {
    const ctx = document.getElementById('spendingHeatmapChart');
    if (!ctx || !data) return;

    if (charts.spendingHeatmap) {
        charts.spendingHeatmap.destroy();
    }

    const labels = data.map(d => d.day_name);
    const amounts = data.map(d => d.total_spending || 0);

    charts.spendingHeatmap = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Total Spending',
                data: amounts,
                backgroundColor: 'rgba(255, 99, 132, 0.8)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: value => 'රු ' + value.toLocaleString()
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const item = data[ctx.dataIndex];
                            return [
                                'Spending: රු ' + ctx.parsed.y.toLocaleString(),
                                'Transactions: ' + (item.transaction_count || 0),
                                'Average: රු ' + (item.avg_amount || 0).toLocaleString()
                            ];
                        }
                    }
                }
            }
        }
    });
}

function updateYearOverYearChart(data) {
    const ctx = document.getElementById('yearOverYearChart');
    if (!ctx || !data) return;

    if (charts.yearOverYear) {
        charts.yearOverYear.destroy();
    }

    // Group by year and month
    const yearGroups = {};
    data.forEach(item => {
        if (!yearGroups[item.year]) {
            yearGroups[item.year] = {};
        }
        yearGroups[item.year][item.month] = item;
    });

    const years = Object.keys(yearGroups).sort();
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    const datasets = years.map((year, idx) => {
        const colors = [
            'rgba(75, 192, 192, 0.8)',
            'rgba(255, 99, 132, 0.8)',
            'rgba(54, 162, 235, 0.8)',
            'rgba(255, 206, 86, 0.8)',
            'rgba(153, 102, 255, 0.8)'
        ];
        const netSavings = months.map((_, monthIdx) => {
            const monthData = yearGroups[year][monthIdx + 1];
            return monthData ? monthData.net_savings : 0;
        });

        return {
            label: year,
            data: netSavings,
            backgroundColor: colors[idx % colors.length],
            borderColor: colors[idx % colors.length].replace('0.8', '1'),
            borderWidth: 2
        };
    });

    charts.yearOverYear = new Chart(ctx, {
        type: 'line',
        data: {
            labels: months,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: value => 'රු ' + value.toLocaleString()
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.dataset.label + ': රු ' + ctx.parsed.y.toLocaleString()
                    }
                }
            }
        }
    });
}

function updateIncomeSourcesChart(data) {
    const ctx = document.getElementById('incomeSourcesPieChart');
    if (!ctx || !data) return;

    if (charts.incomeSources) {
        charts.incomeSources.destroy();
    }

    // Aggregate by category
    const categoryTotals = {};
    data.forEach(item => {
        if (!categoryTotals[item.category]) {
            categoryTotals[item.category] = {
                total: 0,
                count: 0
            };
        }
        categoryTotals[item.category].total += parseFloat(item.total_income || 0);
        categoryTotals[item.category].count += parseInt(item.transaction_count || 0);
    });

    const categories = Object.keys(categoryTotals);
    const amounts = categories.map(cat => categoryTotals[cat].total);

    charts.incomeSources = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: categories,
            datasets: [{
                data: amounts,
                backgroundColor: [
                    'rgba(75, 192, 192, 0.8)',
                    'rgba(54, 162, 235, 0.8)',
                    'rgba(153, 102, 255, 0.8)',
                    'rgba(144, 238, 144, 0.8)',
                    'rgba(135, 206, 250, 0.8)'
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
                    position: 'bottom'
                },
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.label + ': රු ' + ctx.parsed.toLocaleString()
                    }
                }
            }
        }
    });

    // Update table
    const tbody = document.getElementById('incomeSourcesTableBody');
    if (tbody) {
        const rows = Object.entries(categoryTotals).map(([category, data]) => {
            const avg = data.count > 0 ? data.total / data.count : 0;
            return `
                <tr>
                    <td>${category}</td>
                    <td class="text-end">රු ${data.total.toLocaleString()}</td>
                    <td class="text-end">${data.count}</td>
                    <td class="text-end">රු ${avg.toLocaleString()}</td>
                </tr>
            `;
        });
        tbody.innerHTML = rows.join('');
    }
}

function updateTransactionStatusChart(data) {
    if (!data || data.length === 0) return;

    const item = data[0]; // Should be single row for the period

    // Done/Pending chart
    const doneCtx = document.getElementById('transactionDoneChart');
    if (doneCtx) {
        if (charts.transactionDone) {
            charts.transactionDone.destroy();
        }

        charts.transactionDone = new Chart(doneCtx, {
            type: 'doughnut',
            data: {
                labels: ['Completed', 'Pending'],
                datasets: [{
                    data: [item.completed_count || 0, item.pending_count || 0],
                    backgroundColor: ['rgba(75, 192, 192, 0.8)', 'rgba(255, 206, 86, 0.8)'],
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }

    // Paid/Unpaid chart
    const paidCtx = document.getElementById('transactionPaidChart');
    if (paidCtx) {
        if (charts.transactionPaid) {
            charts.transactionPaid.destroy();
        }

        charts.transactionPaid = new Chart(paidCtx, {
            type: 'doughnut',
            data: {
                labels: ['Paid', 'Unpaid'],
                datasets: [{
                    data: [item.paid_count || 0, item.unpaid_count || 0],
                    backgroundColor: ['rgba(75, 192, 192, 0.8)', 'rgba(255, 99, 132, 0.8)'],
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }

    // Update amounts
    const unpaidExpenses = document.getElementById('unpaidExpensesAmount');
    if (unpaidExpenses) {
        unpaidExpenses.textContent = 'රු ' + (item.unpaid_expenses || 0).toLocaleString();
    }

    const unpaidIncome = document.getElementById('unpaidIncomeAmount');
    if (unpaidIncome) {
        unpaidIncome.textContent = 'රු ' + (item.unpaid_income || 0).toLocaleString();
    }
}

function updateExpenseGrowthChart(data) {
    const ctx = document.getElementById('expenseGrowthChart');
    if (!ctx || !data) return;

    if (charts.expenseGrowth) {
        charts.expenseGrowth.destroy();
    }

    // Group by category
    const categories = [...new Set(data.map(d => d.category))];
    const months = [...new Set(data.map(d => d.month))].sort((a, b) => a - b);
    const monthNames = months.map(m => {
        const item = data.find(d => d.month === m);
        return item ? item.month_name.substring(0, 3) : '';
    });

    const datasets = categories.map((category, idx) => {
        const categoryData = months.map(month => {
            const item = data.find(d => d.category === category && d.month === month);
            return item ? item.total_spent : 0;
        });

        const colors = [
            'rgba(255, 99, 132, 0.8)',
            'rgba(54, 162, 235, 0.8)',
            'rgba(255, 206, 86, 0.8)',
            'rgba(75, 192, 192, 0.8)',
            'rgba(153, 102, 255, 0.8)',
            'rgba(255, 159, 64, 0.8)'
        ];

        return {
            label: category,
            data: categoryData,
            backgroundColor: colors[idx % colors.length],
            borderColor: colors[idx % colors.length].replace('0.8', '1'),
            borderWidth: 2
        };
    });

    charts.expenseGrowth = new Chart(ctx, {
        type: 'line',
        data: {
            labels: monthNames,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: value => 'රු ' + value.toLocaleString()
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.dataset.label + ': රු ' + ctx.parsed.y.toLocaleString()
                    }
                }
            }
        }
    });
}

function updateSavingsRateChart(data) {
    const ctx = document.getElementById('savingsRateChart');
    if (!ctx || !data) return;

    if (charts.savingsRate) {
        charts.savingsRate.destroy();
    }

    const labels = data.map(d => d.month_name ? `${d.month_name} ${d.year}` : d.year);
    const income = data.map(d => d.total_income || 0);
    const expenses = data.map(d => d.total_expenses || 0);
    const savingsRate = data.map(d => {
        const inc = d.total_income || 0;
        return inc > 0 ? ((d.net_savings || 0) / inc * 100) : 0;
    });

    charts.savingsRate = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Savings Rate (%)',
                data: savingsRate,
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                borderColor: 'rgba(75, 192, 192, 1)',
                borderWidth: 2,
                fill: true,
                yAxisID: 'y1'
            }, {
                label: 'Income',
                data: income,
                backgroundColor: 'rgba(54, 162, 235, 0.5)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1,
                yAxisID: 'y'
            }, {
                label: 'Expenses',
                data: expenses,
                backgroundColor: 'rgba(255, 99, 132, 0.5)',
                borderColor: 'rgba(255, 99, 132, 1)',
                borderWidth: 1,
                yAxisID: 'y'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    type: 'linear',
                    position: 'left',
                    beginAtZero: true,
                    ticks: {
                        callback: value => 'රු ' + value.toLocaleString()
                    }
                },
                y1: {
                    type: 'linear',
                    position: 'right',
                    beginAtZero: true,
                    grid: {
                        drawOnChartArea: false
                    },
                    ticks: {
                        callback: value => value.toFixed(1) + '%'
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            if (ctx.dataset.label === 'Savings Rate (%)') {
                                return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + '%';
                            }
                            return ctx.dataset.label + ': රු ' + ctx.parsed.y.toLocaleString();
                        }
                    }
                }
            }
        }
    });
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
    const minYear = currentYear - 3;
    const maxYear = currentYear + 3;
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

            // Populate transaction modal dropdown
            const transPaymentMethodSelect = document.getElementById('transPaymentMethod');
            if (transPaymentMethodSelect) {
                // Keep the "None" option and add payment methods
                let optionsHtml = '<option value="">None (Not Paid)</option>';
                paymentMethods.forEach(method => {
                    optionsHtml += `<option value="${method.id}">${method.name}</option>`;
                });
                transPaymentMethodSelect.innerHTML = optionsHtml;
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

    fetch(`/api/transactions/${transactionId}/mark-done`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payment_method_id: paymentMethodId })
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

    fetch(`/api/transactions/${transactionId}/mark-paid`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payment_method_id: paymentMethodId })
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

// Track if we're editing an existing calculation (null if new)
let currentEditingCalculationId = null;

function loadTaxCalculator() {
    console.log('Loading Tax Calculator...');

    // Setup event listeners
    const calculateBtn = document.getElementById('calculateTaxBtn');
    const resetBtn = document.getElementById('resetTaxBtn');
    const assessmentYearSelect = document.getElementById('assessmentYear');
    const startMonthSelect = document.getElementById('startMonth');
    const saveCalculationBtnAlt = document.getElementById('saveCalculationBtnAlt');
    const saveCalculationBtnIncome = document.getElementById('saveCalculationBtnIncome');
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

    if (saveCalculationBtnIncome) {
        saveCalculationBtnIncome.onclick = saveTaxCalculation;
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

    // Sync calculation name fields
    const calculationNameInput = document.getElementById('calculationNameInput');
    const calculationName = document.getElementById('calculationName');

    if (calculationNameInput && calculationName) {
        calculationNameInput.addEventListener('input', function() {
            calculationName.value = this.value;
        });

        calculationName.addEventListener('input', function() {
            calculationNameInput.value = this.value;
        });
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
                                                <span class="input-group-text">රු</span>
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
    // Debug: Check assessment year at start of calculation
    const currentAssessmentYear = document.getElementById('assessmentYear').value;
    console.log('=== CALCULATE TAX STARTED ===');
    console.log('Assessment year dropdown value:', currentAssessmentYear);

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
    document.getElementById('totalUSD').textContent = `රු ${totalUSD.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
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
    const selectedAssessmentYear = document.getElementById('assessmentYear').value;
    console.log('=== CAPTURING ASSESSMENT YEAR ===');
    console.log('Selected assessment year from dropdown:', selectedAssessmentYear);

    lastCalculationData = {
        assessment_year: selectedAssessmentYear,
        tax_rate: 0, // Using progressive brackets (0%, 6%, 15%), not a single rate
        tax_free_threshold: taxFreeThreshold,
        start_month: startMonthIndex,
        monthly_data: monthlyData.map((row, index) => {
            const actualMonthIndex = (startMonthIndex + index) % 12;
            const bonuses = monthlyBonusesData[actualMonthIndex] || [];
            const salaryRateDate = monthlySalaryRateDates[actualMonthIndex] || null;

            // Save both income input data AND calculated tax values
            const monthDataEntry = {
                month_index: index,
                month: row.month,
                salary_usd: monthlySalaries[actualMonthIndex] || 0,
                salary_rate: monthlySalaryRates[actualMonthIndex] || 0,
                salary_rate_date: salaryRateDate,
                bonuses: bonuses,  // Array format: [{amount: 5000, rate: 299, date: '2025-11-21'}, ...]
                // Include calculated values for display in saved calculations
                fcReceiptsUSD: row.fcReceiptsUSD,
                fcReceiptsLKR: row.fcReceiptsLKR,
                cumulativeIncome: row.cumulativeIncome,
                totalTaxLiability: row.totalTaxLiability,
                monthlyPayment: row.monthlyPayment
            };

            if (salaryRateDate) {
                console.log(`Saving month ${actualMonthIndex} (${row.month}) with date: ${salaryRateDate}`);
            }

            return monthDataEntry;
        })
    };

    console.log('Full calculation data to be saved:', JSON.stringify(lastCalculationData.monthly_data, null, 2));

    // Show save section and button
    const saveSection = document.getElementById('saveCalculationSection');
    const saveButtonIncome = document.getElementById('saveCalculationBtnIncome');
    if (saveSection) {
        saveSection.style.display = 'block';

        // Auto-generate calculation name only if not editing
        if (!currentEditingCalculationId) {
            const calcName = `Tax Calculation ${lastCalculationData.assessment_year}`;
            document.getElementById('calculationName').value = calcName;
            document.getElementById('calculationNameInput').value = calcName;
            // For new calculations, default to active
            const setAsActiveCheckbox = document.getElementById('setAsActive');
            if (setAsActiveCheckbox) {
                setAsActiveCheckbox.checked = true;
            }
        }
    }

    // Show the save button in the income details card
    if (saveButtonIncome) {
        saveButtonIncome.style.display = 'flex';
    }

    // Update the active year display
    const activeYearDisplay = document.getElementById('activeYearDisplay');
    if (activeYearDisplay) {
        activeYearDisplay.textContent = lastCalculationData.assessment_year;
    }

    // Update button UI based on editing mode
    updateSaveButtonUI();

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
    document.getElementById('assessmentYear').value = '2026/2027';
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
    document.getElementById('totalUSD').textContent = 'රු 0';
    document.getElementById('totalConverted').textContent = 'රු 0';
    document.getElementById('totalTaxLiability').textContent = 'රු 0';
    document.getElementById('totalMonthlyPayments').textContent = 'රු 0';

    // Reset summary cards
    document.getElementById('annualIncomeSummary').textContent = 'රු 0';
    document.getElementById('taxFreeAmountSummary').textContent = 'රු 360,000';
    document.getElementById('totalTaxSummary').textContent = 'රු 0';
    document.getElementById('effectiveTaxRateSummary').textContent = '0%';

    // Update displays
    updateYearDisplay();

    // Hide save section
    const saveSection = document.getElementById('saveCalculationSection');
    if (saveSection) {
        saveSection.style.display = 'none';
    }

    // Hide save button in Income Details card
    const saveButtonIncome = document.getElementById('saveCalculationBtnIncome');
    if (saveButtonIncome) {
        saveButtonIncome.style.display = 'none';
    }

    // Clear calculation name fields
    document.getElementById('calculationNameInput').value = '';
    document.getElementById('calculationName').value = '';

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

    // Clear editing mode
    currentEditingCalculationId = null;
    updateEditingBanner();
    updateSaveButtonUI();

    showToast('Tax calculator reset', 'info');
}

// Update save button UI based on editing state
function updateSaveButtonUI() {
    const saveBtn = document.getElementById('saveCalculationBtnAlt');
    const saveCard = document.getElementById('saveCalculationCard');
    const saveHeader = document.getElementById('saveCalculationHeader');
    const btnContainer = document.getElementById('saveButtonContainer');
    const editingBanner = document.getElementById('editingStateBanner');

    if (!saveBtn || !saveCard || !saveHeader || !btnContainer) return;

    if (currentEditingCalculationId) {
        // In edit mode - show update UI with IntelliJ dark theme
        saveCard.className = 'card mb-3 border-primary intellij-dark';
        saveHeader.innerHTML = '<i class="fas fa-edit me-2"></i>Update Calculation';
        saveBtn.innerHTML = '<i class="fas fa-save me-2"></i>Update';
        saveBtn.className = 'btn btn-primary flex-grow-1 d-flex align-items-center justify-content-center';
        saveBtn.onclick = () => saveTaxCalculation(false);

        // Add "Save As New" button if it doesn't exist
        if (!document.getElementById('saveAsNewBtn')) {
            const saveAsNewBtn = document.createElement('button');
            saveAsNewBtn.type = 'button';
            saveAsNewBtn.id = 'saveAsNewBtn';
            saveAsNewBtn.className = 'btn btn-outline-success flex-grow-1 d-flex align-items-center justify-content-center';
            saveAsNewBtn.innerHTML = '<i class="fas fa-copy me-2"></i>Save As New Copy';
            saveAsNewBtn.onclick = () => {
                // Suggest a different name for the copy
                const calcNameInput = document.getElementById('calculationName');
                if (calcNameInput && !calcNameInput.value.includes('(Copy)')) {
                    calcNameInput.value = calcNameInput.value + ' (Copy)';
                }
                saveTaxCalculation(true);
            };
            btnContainer.appendChild(saveAsNewBtn);
        }
    } else {
        // In new mode - show save UI with IntelliJ dark theme
        saveCard.className = 'card mb-3 border-success intellij-dark';
        saveHeader.innerHTML = '<i class="fas fa-save me-2"></i>Save New Calculation';
        saveBtn.innerHTML = '<i class="fas fa-save me-2"></i>Save';
        saveBtn.className = 'btn btn-success flex-grow-1 d-flex align-items-center justify-content-center';
        saveBtn.onclick = () => saveTaxCalculation(false);

        // Remove "Save As New" button if it exists
        const saveAsNewBtn = document.getElementById('saveAsNewBtn');
        if (saveAsNewBtn) {
            saveAsNewBtn.remove();
        }
    }
}

// Update editing state banner (removed from UI, kept for compatibility)
function updateEditingBanner(calc = null) {
    // Banner removed from UI - function kept to avoid errors
    return;
}

// Clear editing mode and start fresh
function clearEditingMode() {
    currentEditingCalculationId = null;
    updateSaveButtonUI();
    resetTaxCalculator();
    showToast('Ready to create new calculation', 'info');
}

// ================================
// SAVE AND LOAD CALCULATIONS
// ================================

function saveTaxCalculation(saveAsNew = false) {
    if (!lastCalculationData) {
        showToast('Please calculate tax first before saving', 'warning');
        return;
    }

    // Get calculation name from the input in Income Details card first, fallback to the other field
    let calculationName = document.getElementById('calculationNameInput')?.value.trim();
    if (!calculationName) {
        calculationName = document.getElementById('calculationName')?.value.trim();
    }

    if (!calculationName) {
        showToast('Please enter a name for this calculation', 'warning');
        document.getElementById('calculationNameInput')?.focus();
        return;
    }

    // Keep both fields in sync
    document.getElementById('calculationNameInput').value = calculationName;
    document.getElementById('calculationName').value = calculationName;

    const setAsActive = document.getElementById('setAsActive')?.checked || false;

    // CRITICAL: Always read current form values at save time
    // User might have changed them after calculation but before saving
    const currentAssessmentYear = document.getElementById('assessmentYear').value;
    const currentTaxFreeThreshold = parseFloat(document.getElementById('taxFreeThreshold').value) || 1800000;
    const currentStartMonth = parseInt(document.getElementById('startMonth').value) || 0;

    const dataToSave = {
        ...lastCalculationData,
        assessment_year: currentAssessmentYear, // Override with current dropdown value
        tax_free_threshold: currentTaxFreeThreshold, // Override with current value
        start_month: currentStartMonth, // Override with current value
        calculation_name: calculationName,
        is_active: setAsActive
    };

    console.log('=== SAVING CALCULATION ===');
    console.log('Assessment year from dropdown:', currentAssessmentYear);
    console.log('Assessment year from lastCalculationData:', lastCalculationData.assessment_year);
    console.log('Final assessment year being saved:', dataToSave.assessment_year);
    console.log('Full data object:', dataToSave);

    // Determine if we're updating existing or creating new
    const isUpdate = currentEditingCalculationId && !saveAsNew;

    // CRITICAL: Check for existing active calculation before proceeding
    if (setAsActive) {
        const existingActive = allSavedCalculations.find(calc =>
            calc.assessment_year === currentAssessmentYear &&
            calc.is_active &&
            calc.id !== currentEditingCalculationId
        );

        if (existingActive) {
            const warningMessage = `
                <div class="alert alert-warning">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    <strong>Another calculation is already active for ${currentAssessmentYear}:</strong>
                    <div class="mt-2">
                        <strong>"${existingActive.calculation_name}"</strong>
                    </div>
                </div>
                <p class="mb-0">
                    Setting this calculation as active will automatically <strong>deactivate</strong> the other calculation.
                    Only one calculation can be active per assessment year.
                </p>
                <p class="mt-2 mb-0">Do you want to proceed?</p>
            `;

            showConfirmModal(
                'Confirm Active Calculation Change',
                warningMessage,
                () => {
                    // User confirmed, proceed with save
                    proceedWithSave(dataToSave, isUpdate);
                },
                'Proceed',
                'btn-warning'
            );
            return; // Exit and wait for user confirmation
        }
    }

    // No conflict or not setting as active, proceed directly
    proceedWithSave(dataToSave, isUpdate);
}

function proceedWithSave(dataToSave, isUpdate) {
    const url = isUpdate
        ? `/api/tax-calculations/${currentEditingCalculationId}`
        : '/api/tax-calculations';
    const method = isUpdate ? 'PUT' : 'POST';

    console.log(`=== ${isUpdate ? 'UPDATING' : 'SAVING'} CALCULATION ===`);
    console.log('Data to save:', dataToSave);
    console.log('Monthly data being saved:', dataToSave.monthly_data);
    if (isUpdate) {
        console.log('Updating calculation ID:', currentEditingCalculationId);
    }

    showLoading();

    fetch(url, {
        method: method,
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
            const icon = isUpdate ? '<i class="fas fa-check-circle me-2"></i>' : '<i class="fas fa-save me-2"></i>';
            const message = isUpdate ? 'Tax calculation updated successfully!' : 'Tax calculation saved successfully!';
            showToast(icon + message, 'success');

            // If we just created a new calculation, switch to editing mode for it
            if (!isUpdate && data.id) {
                currentEditingCalculationId = data.id;
                // Fetch the full calculation to update the banner
                fetch(`/api/tax-calculations/${data.id}`)
                    .then(response => response.json())
                    .then(calc => {
                        if (!calc.error) {
                            updateEditingBanner(calc);
                        }
                    });
                updateSaveButtonUI();
            }

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
        const updatedDate = calc.updated_at ? new Date(calc.updated_at).toLocaleDateString() : null;
        const isActive = calc.is_active || false;
        const isCurrentlyEditing = currentEditingCalculationId === calc.id;
        const cardClass = isActive ? 'border-success border-2' : (isCurrentlyEditing ? 'border-primary border-2' : '');
        const bgClass = isActive ? 'bg-success bg-opacity-10' : (isCurrentlyEditing ? 'bg-primary bg-opacity-10' : '');

        // Calculate quarterly and total tax payments from monthly_data
        let quarterlyPayments = [0, 0, 0, 0]; // Q1, Q2, Q3, Q4
        let totalTaxPayment = 0;

        if (calc.monthly_data && Array.isArray(calc.monthly_data)) {
            let previousTaxLiability = 0;

            calc.monthly_data.forEach((monthData, index) => {
                let payment = monthData.monthlyPayment;

                // Fallback: If monthlyPayment is not saved (old calculations), calculate it
                if (payment === undefined || payment === null) {
                    const taxFreeThreshold = calc.tax_free_threshold || 1800000;

                    // Reconstruct cumulative income and tax liability
                    let cumulativeIncome = 0;
                    for (let i = 0; i <= index; i++) {
                        const md = calc.monthly_data[i];
                        const salaryUSD = md.salary_usd || 0;
                        const salaryRate = md.salary_rate || 0;
                        let fcReceiptsLKR = salaryUSD * salaryRate;

                        // Add bonuses
                        if (md.bonuses && Array.isArray(md.bonuses)) {
                            md.bonuses.forEach(bonus => {
                                fcReceiptsLKR += (bonus.amount || 0) * (bonus.rate || 0);
                            });
                        }

                        cumulativeIncome += fcReceiptsLKR;
                    }

                    // Calculate tax liability
                    let totalTaxLiability = 0;
                    if (cumulativeIncome > taxFreeThreshold) {
                        if (cumulativeIncome <= 2_800_000) {
                            totalTaxLiability = (cumulativeIncome - taxFreeThreshold) * 0.06;
                        } else {
                            totalTaxLiability = (2_800_000 - taxFreeThreshold) * 0.06;
                            totalTaxLiability += (cumulativeIncome - 2_800_000) * 0.15;
                        }
                    }

                    payment = Math.max(0, totalTaxLiability - previousTaxLiability);
                    previousTaxLiability = totalTaxLiability;
                } else {
                    payment = payment || 0;
                }

                const quarterIndex = Math.floor(index / 3); // 0-2 -> Q1, 3-5 -> Q2, 6-8 -> Q3, 9-11 -> Q4
                quarterlyPayments[quarterIndex] += payment;
                totalTaxPayment += payment;
            });
        }

        // Build quarterly payment display
        let quarterlyHtml = '';
        quarterlyPayments.forEach((payment, index) => {
            if (payment > 0) {
                quarterlyHtml += `
                    <div class="col-6 col-lg-3">
                        <div class="text-center p-2 bg-light rounded">
                            <small class="text-muted d-block">Q${index + 1}</small>
                            <strong class="small">${formatCurrency(payment)}</strong>
                        </div>
                    </div>
                `;
            }
        });

        html += `
            <div class="list-group-item calculation-item mb-2 ${cardClass} ${bgClass}">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <div class="d-flex align-items-center mb-2">
                            <h6 class="mb-0 me-2">${calc.calculation_name}</h6>
                            ${isActive ? '<span class="badge bg-success"><i class="fas fa-star me-1"></i>Active</span>' : ''}
                            ${isCurrentlyEditing ? '<span class="badge bg-primary ms-2"><i class="fas fa-edit me-1"></i>Editing</span>' : ''}
                        </div>
                        <div class="mb-2">
                            <span class="badge bg-primary me-2">${calc.assessment_year}</span>
                            <span class="text-muted small">
                                <i class="fas fa-calendar-plus me-1"></i>${createdDate}
                                ${updatedDate && updatedDate !== createdDate ? `<i class="fas fa-edit ms-2 me-1"></i>${updatedDate}` : ''}
                            </span>
                        </div>
                        <div class="row g-2 small mb-2">
                            <div class="col-auto">
                                <span class="text-muted">Tax-Free Threshold:</span>
                                <strong class="ms-1">${formatCurrency(calc.tax_free_threshold)}</strong>
                            </div>
                        </div>
                        ${totalTaxPayment > 0 ? `
                        <div class="mb-2">
                            <div class="d-flex align-items-center mb-2">
                                <i class="fas fa-file-invoice-dollar me-2 text-danger"></i>
                                <span class="text-muted small">Total Tax:</span>
                                <strong class="ms-2 text-danger">${formatCurrency(totalTaxPayment)}</strong>
                            </div>
                        </div>
                        ${quarterlyHtml ? `
                        <div class="row g-2 small">
                            ${quarterlyHtml}
                        </div>
                        ` : ''}
                        ` : ''}
                    </div>
                    <div class="ms-3 d-flex align-items-center">
                        <div class="btn-group-vertical" role="group">
                            <button class="btn btn-sm ${isCurrentlyEditing ? 'btn-primary' : 'btn-outline-primary'} d-flex align-items-center justify-content-center"
                                    onclick="loadCalculation(${calc.id})"
                                    title="${isCurrentlyEditing ? 'Currently loaded' : 'Load this calculation'}">
                                <i class="fas fa-download me-1"></i>Load
                            </button>
                            <button class="btn btn-sm ${isActive ? 'btn-success' : 'btn-outline-success'} d-flex align-items-center justify-content-center"
                                    onclick="toggleActiveCalculation(${calc.id}, ${isActive})"
                                    title="${isActive ? 'Deactivate this calculation' : 'Set as active for ' + calc.assessment_year}">
                                <i class="fas ${isActive ? 'fa-check' : 'fa-star'} me-1"></i>${isActive ? 'Active' : 'Activate'}
                            </button>
                            <button class="btn btn-sm btn-outline-danger d-flex align-items-center justify-content-center"
                                    onclick="deleteCalculation(${calc.id})"
                                    title="Delete this calculation">
                                <i class="fas fa-trash me-1"></i>Delete
                            </button>
                        </div>
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
    // Find the calculation being activated
    const calcToActivate = allSavedCalculations.find(c => c.id === calculationId);
    if (!calcToActivate) {
        showToast('Calculation not found', 'danger');
        return;
    }

    // Find any existing active calculation for the same year
    const existingActive = allSavedCalculations.find(calc =>
        calc.assessment_year === calcToActivate.assessment_year &&
        calc.is_active &&
        calc.id !== calculationId
    );

    let warningMessage = `<p class="mb-2">Set <strong>"${calcToActivate.calculation_name}"</strong> as active for ${calcToActivate.assessment_year}?</p>`;

    if (existingActive) {
        warningMessage += `
            <div class="alert alert-warning mb-0">
                <i class="fas fa-exclamation-triangle me-2"></i>
                <strong>Note:</strong> This will automatically deactivate:<br>
                <strong class="mt-1 d-block">"${existingActive.calculation_name}"</strong>
                <small class="d-block mt-1 text-muted">Only one calculation can be active per assessment year.</small>
            </div>
        `;
    } else {
        warningMessage += `
            <div class="alert alert-info mb-0">
                <i class="fas fa-info-circle me-2"></i>
                This calculation will become the active calculation for ${calcToActivate.assessment_year}.
            </div>
        `;
    }

    showConfirmModal(
        'Set Active Calculation',
        warningMessage,
        () => {
            showLoading();

            fetch(`/api/tax-calculations/${calculationId}/set-active`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                hideLoading();
                if (data.error) {
                    showToast(data.error, 'danger');
                } else {
                    showToast(
                        `<i class="fas fa-star me-2"></i>Calculation activated for ${data.assessment_year}!`,
                        'success'
                    );
                    // Reload the calculations list to reflect the change
                    loadSavedCalculations();
                }
            })
            .catch(error => {
                hideLoading();
                console.error('Error setting active calculation:', error);
                showToast('Failed to set active calculation', 'danger');
            });
        },
        'Activate',
        'btn-success'
    );
}

function toggleActiveCalculation(calculationId, isCurrentlyActive) {
    const calcToToggle = allSavedCalculations.find(c => c.id === calculationId);
    if (!calcToToggle) {
        showToast('Calculation not found', 'danger');
        return;
    }

    if (isCurrentlyActive) {
        // Deactivate
        showConfirmModal(
            'Deactivate Calculation',
            `<p class="mb-2">Deactivate <strong>"${calcToToggle.calculation_name}"</strong> for ${calcToToggle.assessment_year}?</p>
            <div class="alert alert-info mb-0">
                <i class="fas fa-info-circle me-2"></i>
                This calculation will no longer be marked as active.
            </div>`,
            () => {
                showLoading();

                fetch(`/api/tax-calculations/${calculationId}/deactivate`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                })
                .then(response => response.json())
                .then(data => {
                    hideLoading();
                    if (data.error) {
                        showToast(data.error, 'danger');
                    } else {
                        showToast(
                            `<i class="fas fa-times-circle me-2"></i>Calculation deactivated for ${data.assessment_year}!`,
                            'info'
                        );
                        loadSavedCalculations();
                    }
                })
                .catch(error => {
                    hideLoading();
                    console.error('Error deactivating calculation:', error);
                    showToast('Failed to deactivate calculation', 'danger');
                });
            },
            'Deactivate',
            'btn-warning'
        );
    } else {
        // Activate (use existing function)
        setActiveCalculation(calculationId);
    }
}

function loadCalculation(calculationId) {
    showLoading();

    // Set editing mode
    currentEditingCalculationId = calculationId;

    fetch(`/api/tax-calculations/${calculationId}`)
    .then(response => response.json())
    .then(calc => {
        hideLoading();

        if (calc.error) {
            showToast(calc.error, 'danger');
            currentEditingCalculationId = null;
            updateEditingBanner();
            return;
        }

        // Update editing banner with calculation details
        updateEditingBanner(calc);

        console.log('=== LOADING CALCULATION ===');
        console.log('ID:', calc.id, '| Name:', calc.calculation_name);
        console.log('Year:', calc.assessment_year, '| Threshold:', calc.tax_free_threshold);
        console.log('Start month:', calc.start_month);
        console.log('Active status:', calc.is_active);
        console.log('Monthly data entries:', calc.monthly_data ? calc.monthly_data.length : 0);

        // Load values into form fields
        document.getElementById('calculationName').value = calc.calculation_name;
        document.getElementById('calculationNameInput').value = calc.calculation_name;
        document.getElementById('assessmentYear').value = calc.assessment_year;
        // Tax rate is now hardcoded in progressive brackets, not loaded from saved data
        document.getElementById('taxFreeThreshold').value = calc.tax_free_threshold;
        document.getElementById('startMonth').value = calc.start_month;

        // Set the "Set as active" checkbox based on current status
        const setAsActiveCheckbox = document.getElementById('setAsActive');
        if (setAsActiveCheckbox) {
            setAsActiveCheckbox.checked = calc.is_active || false;
        }

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

            // Update save button UI to show "Update" mode
            updateSaveButtonUI();
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
    const isCurrentlyEditing = currentEditingCalculationId === calculationId;
    const warningMsg = isCurrentlyEditing
        ? '<div class="alert alert-warning mb-3"><i class="fas fa-exclamation-triangle me-2"></i>You are currently editing this calculation. Deleting it will clear your current work.</div>'
        : '';

    showConfirmModal(
        'Delete Calculation',
        warningMsg + 'Are you sure you want to delete this calculation? This action cannot be undone.',
        () => {
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
                    showToast('<i class="fas fa-trash me-2"></i>Calculation deleted successfully', 'success');

                    // If we were editing this calculation, clear the editing state
                    if (isCurrentlyEditing) {
                        clearEditingMode();
                    }

                    loadSavedCalculations();
                }
            })
            .catch(error => {
                hideLoading();
                console.error('Error deleting calculation:', error);
                showToast('Failed to delete calculation', 'danger');
            });
        },
        'Delete',
        'btn-danger'
    );
}

// Note: formatCurrency, formatDate, showLoading, hideLoading, showToast
// are defined in base.html and available globally

// Bill upload functionality
document.addEventListener('DOMContentLoaded', function() {
    const uploadBillBtn = document.getElementById('uploadBillBtn');
    const billUploadInput = document.getElementById('billUploadInput');
    const scanStatus = document.getElementById('scanStatus');
    const scanStatusText = document.getElementById('scanStatusText');

    // Handle upload bill button click
    if (uploadBillBtn && billUploadInput) {
        uploadBillBtn.addEventListener('click', function() {
            console.log('Upload bill button clicked');
            billUploadInput.click();
        });
    }

    // Handle file selection
    if (billUploadInput) {
        billUploadInput.addEventListener('change', async function(event) {
            const files = Array.from(event.target.files);
            if (!files || files.length === 0) {
                console.log('No file selected');
                return;
            }

            console.log(`${files.length} file(s) selected`);

            // Validate maximum number of files (5 max)
            const MAX_FILES = 5;
            if (files.length > MAX_FILES) {
                showToast(`Maximum ${MAX_FILES} images allowed per scan`, 'danger');
                billUploadInput.value = '';
                return;
            }

            // Validate each file
            const allowedTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp', 'application/pdf'];
            const maxSize = 50 * 1024 * 1024;

            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                console.log(`File ${i + 1}/${files.length}:`, file.name, file.type, file.size);

                if (!allowedTypes.includes(file.type)) {
                    showToast(`Invalid file type for "${file.name}". Allowed: PNG, JPEG, GIF, WebP, or PDF`, 'danger');
                    billUploadInput.value = '';
                    return;
                }

                if (file.size > maxSize) {
                    showToast(`File "${file.name}" is too large. Please select files under 50MB`, 'danger');
                    billUploadInput.value = '';
                    return;
                }
            }

            // Open the transaction modal immediately
            const transactionModal = new bootstrap.Modal(document.getElementById('transactionModal'));
            transactionModal.show();

            // Show scanning status inside the modal
            const fileCountText = files.length > 1 ? ` (${files.length} images)` : '';
            if (scanStatus && scanStatusText) {
                scanStatus.style.display = 'block';
                scanStatusText.textContent = `Compressing & scanning bill${fileCountText}...`;
            }

            // Hide any previous bill breakdown
            const billBreakdown = document.getElementById('billBreakdown');
            if (billBreakdown) {
                billBreakdown.style.display = 'none';
            }

            // Disable upload button during processing
            if (uploadBillBtn) {
                uploadBillBtn.disabled = true;
                uploadBillBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Scanning...';
            }

            try {
                // Compress all images first
                const compressedFiles = [];

                for (let i = 0; i < files.length; i++) {
                    const file = files[i];

                    if (scanStatusText && files.length > 1) {
                        scanStatusText.textContent = `Compressing image ${i + 1}/${files.length}...`;
                    }

                    const { fileToSend, wasCompressed } = await compressFileForUpload(file);
                    compressedFiles.push(fileToSend);
                }

                // Scan based on upload mode configuration
                let scanResults = [];

                console.log(`[Bill Scan Mode Check] uploadMode: '${uploadMode}', Images: ${compressedFiles.length}`);

                if (uploadMode === 'batch') {
                    // BATCH MODE: Send all images in one request
                    if (scanStatusText) {
                        scanStatusText.textContent = `Scanning ${compressedFiles.length} image(s)...`;
                    }

                    const formData = new FormData();
                    compressedFiles.forEach((file, idx) => {
                        formData.append('bill_images', file, file.name || `image_${idx + 1}.jpg`);
                    });

                    console.log(`[Batch Mode] Sending ${compressedFiles.length} image(s) to API in one request...`);
                    const response = await fetch('/api/scan-bill', {
                        method: 'POST',
                        body: formData
                    });

                    if (response.status === 413) {
                        throw new Error('Images are too large. Please use smaller images or switch to Sequential mode.');
                    }

                    const result = await response.json();
                    console.log('Batch scan API response:', result);

                    if (!response.ok) {
                        throw new Error(result.error || 'Failed to scan images');
                    }

                    if (result.success) {
                        // Server already merged results for us
                        scanResults = [result];
                    } else {
                        throw new Error(result.error || 'Failed to extract data from images');
                    }

                } else {
                    // SEQUENTIAL MODE: Send each image separately
                    for (let i = 0; i < compressedFiles.length; i++) {
                        if (scanStatusText) {
                            scanStatusText.textContent = `Scanning image ${i + 1}/${compressedFiles.length}...`;
                        }

                        const formData = new FormData();
                        formData.append('bill_images', compressedFiles[i], compressedFiles[i].name || `image_${i + 1}.jpg`);

                        console.log(`[Sequential Mode] Sending image ${i + 1}/${compressedFiles.length} to API (${(compressedFiles[i].size / (1024*1024)).toFixed(1)} MB)...`);
                        const response = await fetch('/api/scan-bill', {
                            method: 'POST',
                            body: formData
                        });

                        if (response.status === 413) {
                            throw new Error(`Image ${i + 1} is too large. Please use a smaller image.`);
                        }

                        const result = await response.json();
                        console.log(`API response for image ${i + 1}:`, result);

                        if (!response.ok) {
                            throw new Error(result.error || `Failed to scan image ${i + 1}`);
                        }

                        if (result.success) {
                            scanResults.push(result);
                        } else {
                            throw new Error(result.error || `Failed to extract data from image ${i + 1}`);
                        }
                    }
                }

                // Handle results based on number of images scanned
                let mergedResult;

                if (scanResults.length === 1) {
                    // Single image - use result directly without deduplication
                    mergedResult = scanResults[0];
                    console.log('Single image scan:', mergedResult);
                } else {
                    // Multiple images - merge and deduplicate results
                    mergedResult = {
                        shop_name: scanResults[0]?.shop_name || 'Unknown Store',
                        amount: '0',
                        subtotal: '0',
                        discounts: [],
                        items: []
                    };

                    let totalAmount = 0;
                    let totalSubtotal = 0;
                    const seenDiscounts = {}; // Track unique discounts by description

                    for (const result of scanResults) {
                        // For multi-image scans of the SAME receipt, take the highest amount/subtotal
                        // (not sum, since all images are of the same receipt)
                        const amount = parseFloat(result.amount) || 0;
                        const subtotal = parseFloat(result.subtotal) || 0;
                        totalAmount = Math.max(totalAmount, amount);
                        totalSubtotal = Math.max(totalSubtotal, subtotal);

                        // Merge items arrays - fuzzy deduplicate to handle OCR errors
                        // But respect item codes - same name + different code = different items
                        if (result.items && result.items.length > 0) {
                            result.items.forEach(item => {
                                const itemCode = (item.code || '').trim();

                                // Check if this item is similar to any existing item
                                let isDuplicate = false;
                                for (let i = 0; i < mergedResult.items.length; i++) {
                                    const existingCode = (mergedResult.items[i].code || '').trim();

                                    // If both have codes, they must match
                                    if (itemCode && existingCode) {
                                        if (itemCode === existingCode && areItemsSimilar(item.name, mergedResult.items[i].name)) {
                                            isDuplicate = true;
                                            // Keep the longer/more complete name
                                            if (item.name.length > mergedResult.items[i].name.length) {
                                                mergedResult.items[i] = item;
                                            }
                                            break;
                                        }
                                    }
                                    // If only one has a code, treat as different items
                                    else if (itemCode || existingCode) {
                                        continue;
                                    }
                                    // If neither has a code, check name similarity only
                                    else {
                                        if (areItemsSimilar(item.name, mergedResult.items[i].name)) {
                                            isDuplicate = true;
                                            // Keep the longer/more complete name
                                            if (item.name.length > mergedResult.items[i].name.length) {
                                                mergedResult.items[i] = item;
                                            }
                                            break;
                                        }
                                    }
                                }

                                if (!isDuplicate) {
                                    mergedResult.items.push(item);
                                }
                            });
                        }

                        // Merge discounts arrays - deduplicate by description
                        if (result.discounts && result.discounts.length > 0) {
                            result.discounts.forEach(discount => {
                                const discountKey = (discount.description || '').toLowerCase().trim();
                                if (discountKey && !seenDiscounts[discountKey]) {
                                    seenDiscounts[discountKey] = true;
                                    mergedResult.discounts.push(discount);
                                }
                            });
                        }
                    }

                    mergedResult.amount = totalAmount.toFixed(2);
                    mergedResult.subtotal = totalSubtotal.toFixed(2);

                    console.log('Merged result from', scanResults.length, 'images:', mergedResult);
                    console.log(`Deduplicated to ${mergedResult.items.length} unique items and ${mergedResult.discounts.length} unique discounts`);
                }

                // Store the merged scanned bill content
                scannedBillContent = {
                    shop_name: mergedResult.shop_name,
                    amount: mergedResult.amount,
                    subtotal: mergedResult.subtotal,
                    discounts: mergedResult.discounts,
                    items: mergedResult.items
                };

                // Store ALL compressed files for upload when transaction is saved
                capturedBillImages = compressedFiles;
                console.log(`Stored ${capturedBillImages.length} bill image(s) for upload`);

                // Populate the form with extracted data
                const transDescription = document.getElementById('transDescription');
                const transCredit = document.getElementById('transCredit');

                if (mergedResult.shop_name && mergedResult.shop_name !== 'Unknown Store' && transDescription) {
                    transDescription.value = mergedResult.shop_name;
                }

                if (mergedResult.amount && parseFloat(mergedResult.amount) > 0 && transCredit) {
                    transCredit.value = mergedResult.amount;
                }

                // Display bill breakdown
                displayBillBreakdown(mergedResult);

                // Show success message
                const itemCount = mergedResult.items.length;
                const discountCount = mergedResult.discounts.length;
                const itemText = itemCount > 0 ? ` (${itemCount} items)` : '';
                const discountText = discountCount > 0 ? ` with ${discountCount} discount${discountCount > 1 ? 's' : ''}` : '';
                const multiImageText = files.length > 1 ? ` from ${files.length} images` : '';

                if (scanStatusText) {
                    scanStatusText.textContent = `✓ Bill scanned successfully!${itemText}${discountText}${multiImageText}`;
                }
                if (scanStatus) {
                    scanStatus.style.color = '#28a745';
                }

                setTimeout(() => {
                    if (scanStatus) {
                        scanStatus.style.display = 'none';
                        scanStatus.style.color = '#ffc107';
                    }
                }, 3000);

                showToast(`Bill scanned: ${mergedResult.shop_name} - රු ${mergedResult.amount}${itemText}${discountText}`, 'success');

            } catch (error) {
                console.error('Error scanning bill:', error);

                if (scanStatusText) {
                    scanStatusText.textContent = '✗ Scan failed';
                }
                if (scanStatus) {
                    scanStatus.style.color = '#dc3545';
                }

                setTimeout(() => {
                    if (scanStatus) {
                        scanStatus.style.display = 'none';
                        scanStatus.style.color = '#ffc107';
                    }
                }, 5000);

                showToast(error.message || 'Failed to scan bill. Please enter details manually.', 'danger');
            } finally {
                // Reset button and input
                if (uploadBillBtn) {
                    uploadBillBtn.disabled = false;
                    uploadBillBtn.innerHTML = '<i class="fas fa-file-upload me-1"></i>Upload Bill';
                }
                billUploadInput.value = '';
            }
        });
    }
});
