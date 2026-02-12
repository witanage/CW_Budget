// Check if user is on mobile device
function isMobileDevice() {
return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
(window.innerWidth <= 768);
}

document.getElementById('loginForm').addEventListener('submit', function(e) {
e.preventDefault();

// Show loader and disable button
const loginButton = document.getElementById('loginButton');
const loginSpinner = document.getElementById('loginSpinner');
const loginButtonText = document.getElementById('loginButtonText');

loginButton.disabled = true;
loginSpinner.classList.remove('d-none');
loginButtonText.textContent = 'Logging in...';

const formData = {
username: document.getElementById('username').value,
password: document.getElementById('password').value,
remember_me: document.getElementById('rememberMe').checked
};

fetch('/login', {
method: 'POST',
headers: {
'Content-Type': 'application/json',
},
credentials: 'same-origin',
body: JSON.stringify(formData)
})
.then(response => response.json())
.then(data => {
if (data.error) {
// Hide loader and enable button on error
loginButton.disabled = false;
loginSpinner.classList.add('d-none');
loginButtonText.textContent = 'Login';
showToast(data.error, 'danger');
} else {
showToast('Login successful! Redirecting...', 'success');
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
// Hide loader and enable button on error
loginButton.disabled = false;
loginSpinner.classList.add('d-none');
loginButtonText.textContent = 'Login';
console.error('Error:', error);
showToast('An error occurred during login', 'danger');
});
});
