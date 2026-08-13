// MFA Verification JavaScript

// Check if user is on mobile device
function isMobileDevice() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
           (window.innerWidth <= 768);
}

// Toggle between authenticator and backup code forms
document.getElementById('useBackupCodeButton').addEventListener('click', function() {
    document.getElementById('mfaVerifyForm').classList.add('d-none');
    document.getElementById('backupCodeForm').classList.remove('d-none');
    document.getElementById('backupCode').focus();
});

document.getElementById('useAuthenticatorButton').addEventListener('click', function() {
    document.getElementById('backupCodeForm').classList.add('d-none');
    document.getElementById('mfaVerifyForm').classList.remove('d-none');
    document.getElementById('verificationCode').focus();
});

// Verify authenticator code
document.getElementById('mfaVerifyForm').addEventListener('submit', function(e) {
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

    fetch('/mfa/verify', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({
            code: code,
            use_backup: false
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showToast(data.error, 'danger');
            verifyButton.disabled = false;
            verifySpinner.classList.add('d-none');
            verifyButtonText.textContent = 'Verify';
            document.getElementById('verificationCode').value = '';
            document.getElementById('verificationCode').focus();
        } else {
            showToast('Verification successful! Redirecting...', 'success');
            setTimeout(() => {
                // Redirect to mobile view if on mobile device
                if (isMobileDevice()) {
                    window.location.href = '/mobile';
                } else {
                    window.location.href = '/dashboard';
                }
            }, 1000);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Verification failed', 'danger');
        verifyButton.disabled = false;
        verifySpinner.classList.add('d-none');
        verifyButtonText.textContent = 'Verify';
    });
});

// Verify backup code
document.getElementById('backupCodeForm').addEventListener('submit', function(e) {
    e.preventDefault();

    const verifyButton = document.getElementById('backupVerifyButton');
    const verifySpinner = document.getElementById('backupVerifySpinner');
    const verifyButtonText = document.getElementById('backupVerifyButtonText');
    const code = document.getElementById('backupCode').value;

    // Validate code format
    if (!/^\d{8}$/.test(code)) {
        showToast('Please enter a valid 8-digit backup code', 'warning');
        return;
    }

    verifyButton.disabled = true;
    verifySpinner.classList.remove('d-none');
    verifyButtonText.textContent = 'Verifying...';

    fetch('/mfa/verify', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({
            code: code,
            use_backup: true
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showToast(data.error, 'danger');
            verifyButton.disabled = false;
            verifySpinner.classList.add('d-none');
            verifyButtonText.textContent = 'Verify Backup Code';
            document.getElementById('backupCode').value = '';
            document.getElementById('backupCode').focus();
        } else {
            showToast('Verification successful! Redirecting...', 'success');
            setTimeout(() => {
                // Redirect to mobile view if on mobile device
                if (isMobileDevice()) {
                    window.location.href = '/mobile';
                } else {
                    window.location.href = '/dashboard';
                }
            }, 1000);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Verification failed', 'danger');
        verifyButton.disabled = false;
        verifySpinner.classList.add('d-none');
        verifyButtonText.textContent = 'Verify Backup Code';
    });
});

// Auto-format verification code input (6 digits)
document.getElementById('verificationCode').addEventListener('input', function(e) {
    this.value = this.value.replace(/\D/g, '');
    if (this.value.length > 6) {
        this.value = this.value.slice(0, 6);
    }
});

// Auto-format backup code input (8 digits)
document.getElementById('backupCode').addEventListener('input', function(e) {
    this.value = this.value.replace(/\D/g, '');
    if (this.value.length > 8) {
        this.value = this.value.slice(0, 8);
    }
});
