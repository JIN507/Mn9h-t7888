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
    
    // Check for pending images from video frames
    checkForPendingImages();
});

// Function to check for pending images from video frames
function checkForPendingImages() {
    // Check for reverse search from video
    const pendingReverseSearch = localStorage.getItem('pendingReverseSearch');
    if (pendingReverseSearch && window.location.pathname === '/') {
        // Auto-populate the reverse search form
        populateImageForm(pendingReverseSearch);
        localStorage.removeItem('pendingReverseSearch');
    }
    
    // Check for provenance from video
    const pendingProvenance = localStorage.getItem('pendingProvenance');
    if (pendingProvenance && window.location.pathname === '/provenance') {
        // Auto-populate the provenance form
        populateProvenanceForm(pendingProvenance);
        localStorage.removeItem('pendingProvenance');
    }
}

// Function to populate reverse search form with image data
function populateImageForm(imageData) {
    const previewContainer = document.getElementById('preview-container');
    const imagePreview = document.getElementById('image-preview');
    const dropArea = document.getElementById('drop-area');
    
    if (previewContainer && imagePreview && dropArea) {
        imagePreview.src = imageData;
        previewContainer.classList.remove('d-none');
        dropArea.classList.add('d-none');
        
        // Store the image data for form submission
        window.uploadedImageData = imageData;
    }
}

// Function to populate provenance form with image data
function populateProvenanceForm(imageData) {
    // Wait for DOM to be ready
    setTimeout(() => {
        const imageUrlInput = document.getElementById('image_url');
        const imagePreview = document.getElementById('imagePreview');
        const previewImg = document.getElementById('previewImg');
        const fileDropArea = document.getElementById('fileDropArea');
        
        if (imageUrlInput && imagePreview && previewImg) {
            imageUrlInput.value = imageData;
            previewImg.src = imageData;
            imagePreview.style.display = 'block';
            
            // Hide the file drop area since we have an image
            if (fileDropArea) {
                fileDropArea.style.display = 'none';
            }
            
            // Store the image data for form submission
            window.uploadedImageData = imageData;
            
            console.log('Provenance form populated with video frame');
        } else {
            console.error('Provenance form elements not found:', {
                imageUrlInput: !!imageUrlInput,
                imagePreview: !!imagePreview,
                previewImg: !!previewImg,
                fileDropArea: !!fileDropArea
            });
        }
    }, 100);
}
