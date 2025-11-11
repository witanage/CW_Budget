document.getElementById('registerForm').addEventListener('submit', function(e) {
e.preventDefault();

const password = document.getElementById('password').value;
const confirmPassword = document.getElementById('confirmPassword').value;

if (password !== confirmPassword) {
showToast('Passwords do not match', 'danger');
return;
}

const formData = {
username: document.getElementById('username').value,
email: document.getElementById('email').value,
password: password
};

fetch('/register', {
method: 'POST',
headers: {
'Content-Type': 'application/json',
},
body: JSON.stringify(formData)
})
.then(response => response.json())
.then(data => {
if (data.error) {
showToast(data.error, 'danger');
} else {
showToast('Registration successful! Redirecting to login...', 'success');
setTimeout(() => {
window.location.href = '/login';
}, 2000);
}
})
.catch(error => {
console.error('Error:', error);
showToast('An error occurred during registration', 'danger');
});
});
