// Bahith Al-Suwar - Main JavaScript File

document.addEventListener('DOMContentLoaded', function() {
    // Add current year to footer
    const yearElement = document.querySelector('footer .text-muted');
    if (yearElement) {
        const currentYear = new Date().getFullYear();
        yearElement.innerHTML = yearElement.innerHTML.replace('{new Date().getFullYear()}', currentYear);
    }
    
    // Add Bootstrap classes to all tables
    const tables = document.querySelectorAll('table');
    tables.forEach(table => {
        table.classList.add('table', 'table-striped', 'table-bordered');
    });
    
    // Add Bootstrap classes to form elements
    const inputs = document.querySelectorAll('input[type="text"], input[type="email"], input[type="password"], textarea');
    inputs.forEach(input => {
        input.classList.add('form-control');
    });
    
    // Add Arabic font if needed
    if (document.documentElement.lang === 'ar') {
        const link = document.createElement('link');
        link.href = 'https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap';
        link.rel = 'stylesheet';
        document.head.appendChild(link);
    }
});
