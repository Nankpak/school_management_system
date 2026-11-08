// Initialize shared interactions after the page markup is available.
document.addEventListener('DOMContentLoaded', function () {
	// Show or hide the sidebar on small screens.
	const toggle = document.getElementById('menuToggle');
	const sidebar = document.getElementById('sidebar');
	if (toggle && sidebar) {
		toggle.addEventListener('click', function () {
			sidebar.classList.toggle('open');
		});
	}

	// Reveal or mask a password field and update the control's label.
	document.querySelectorAll('[data-toggle-password]').forEach(function (button) {
		button.addEventListener('click', function () {
			const input = document.querySelector(button.dataset.togglePassword);
			if (input) {
				input.type = input.type === 'password' ? 'text' : 'password';
				button.textContent = input.type === 'password' ? 'Show' : 'Hide';
			}
		});
	});

	// Open the modal identified by the clicked trigger's data-modal value.
	document.querySelectorAll('[data-modal]').forEach(function (button) {
		const modal = document.getElementById(button.dataset.modal);
		button.addEventListener('click', function () {
			modal.classList.add('open');
		});
	});

	// Close the nearest modal when one of its close controls is activated.
	document.querySelectorAll('[data-close]').forEach(function (button) {
		button.addEventListener('click', function () {
			button.closest('.modal').classList.remove('open');
		});
	});
});