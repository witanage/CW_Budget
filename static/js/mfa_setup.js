// MFA Setup JavaScript

let mfaSecret = null;
let backupCodes = [];

// Step navigation
function showStep(stepNumber) {
    document.querySelectorAll('.mfa-step').forEach(step => step.classList.add('d-none'));
    document.getElementById(`step${stepNumber}`).classList.remove('d-none');
}

// Generate QR Code
document.getElementById('generateQRButton').addEventListener('click', function() {
    const button = this;
    button.disabled = true;
    button.innerHTML = '<span class="professional-spinner-sm me-2"></span>Generating...';

    fetch('/api/mfa/setup', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showToast(data.error, 'danger');
            button.disabled = false;
            button.innerHTML = '<i class="fas fa-qrcode me-2"></i>Generate QR Code';
        } else {
            // Display QR code
            document.getElementById('qrCodeImage').src = data.qr_code;
            document.getElementById('manualSecret').textContent = data.secret;
            mfaSecret = data.secret;

            document.getElementById('qrCodeContainer').classList.remove('d-none');
            button.classList.add('d-none');

            showToast('QR Code generated successfully', 'success');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Failed to generate QR code', 'danger');
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-qrcode me-2"></i>Generate QR Code';
    });
});

// Proceed to verification step
document.getElementById('proceedToVerifyButton').addEventListener('click', function() {
    showStep(2);
    document.getElementById('verificationCode').focus();
});

// Back to QR code
document.getElementById('backToQRButton').addEventListener('click', function() {
    showStep(1);
});

// Verify and enable MFA
document.getElementById('verifyForm').addEventListener('submit', function(e) {
    e.preventDefault();

    const verifyButton = document.getElementById('verifyButton');
    const verifySpinner = document.getElementById('verifySpinner');
    const verifyButtonText = document.getElementById('verifyButtonText');
    const code = document.getElementById('verificationCode').value;

    // Validate code format
    if (!/^\d{6}$/.test(code)) {
        showToast('Please enter a valid 6-digit code', 'warning');
        return;
    }

    verifyButton.disabled = true;
    verifySpinner.classList.remove('d-none');
    verifyButtonText.textContent = 'Verifying...';

    fetch('/api/mfa/verify-setup', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ code: code })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showToast(data.error, 'danger');
            verifyButton.disabled = false;
            verifySpinner.classList.add('d-none');
            verifyButtonText.textContent = 'Verify & Enable MFA';
            document.getElementById('verificationCode').value = '';
            document.getElementById('verificationCode').focus();
        } else {
            // Store backup codes and show step 3
            backupCodes = data.backup_codes;
            displayBackupCodes();
            showStep(3);
            showToast('MFA enabled successfully!', 'success');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Verification failed', 'danger');
        verifyButton.disabled = false;
        verifySpinner.classList.add('d-none');
        verifyButtonText.textContent = 'Verify & Enable MFA';
    });
});

// Display backup codes
function displayBackupCodes() {
    const container = document.getElementById('backupCodesContainer');
    let html = '<div class="row g-2">';

    backupCodes.forEach((code, index) => {
        html += `
            <div class="col-6">
                <div class="alert alert-secondary mb-0 py-2">
                    <strong>${index + 1}.</strong> <code>${code}</code>
                </div>
            </div>
        `;
    });

    html += '</div>';
    container.innerHTML = html;
}

// Copy backup codes to clipboard
document.getElementById('copyBackupCodesButton').addEventListener('click', function() {
    const codesText = backupCodes.join('\n');

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(codesText)
            .then(() => {
                showToast('Backup codes copied to clipboard', 'success');
                this.innerHTML = '<i class="fas fa-check me-2"></i>Copied!';
                setTimeout(() => {
                    this.innerHTML = '<i class="fas fa-copy me-2"></i>Copy Backup Codes';
                }, 2000);
            })
            .catch(err => {
                console.error('Failed to copy:', err);
                showToast('Failed to copy codes', 'danger');
            });
    } else {
        // Fallback for older browsers
        const textarea = document.createElement('textarea');
        textarea.value = codesText;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand('copy');
            showToast('Backup codes copied to clipboard', 'success');
            this.innerHTML = '<i class="fas fa-check me-2"></i>Copied!';
            setTimeout(() => {
                this.innerHTML = '<i class="fas fa-copy me-2"></i>Copy Backup Codes';
            }, 2000);
        } catch (err) {
            console.error('Failed to copy:', err);
            showToast('Failed to copy codes', 'danger');
        }
        document.body.removeChild(textarea);
    }
});

// Finish setup and redirect to dashboard
document.getElementById('finishButton').addEventListener('click', function() {
    window.location.href = '/dashboard';
});

// Auto-focus and format verification code input
document.getElementById('verificationCode').addEventListener('input', function(e) {
    // Remove non-digit characters
    this.value = this.value.replace(/\D/g, '');

    // Limit to 6 digits
    if (this.value.length > 6) {
        this.value = this.value.slice(0, 6);
    }
});
