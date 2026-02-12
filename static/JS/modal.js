function openModal(imageSrc) {
    const modal = document.getElementById('imageModal');
    const modalImg = document.getElementById('modalImage');
    
    if (modal && modalImg) {
        modalImg.src = imageSrc;
        modal.classList.add('active');
        // Prevent background scrolling while viewing image
        document.body.style.overflow = 'hidden'; 
    }
}

function closeModal(event) {
    const modal = document.getElementById('imageModal');
    
    if (modal) {
        // Prevent closing if the user clicks the image content itself
        if (event && event.target.id === 'modalImage') {
            return;
        }
        
        modal.classList.remove('active');
        // Restore background scrolling
        document.body.style.overflow = ''; 
    }
}

// Global Event Listeners for better User Experience
document.addEventListener('keydown', function(event) {
    // Close modal on Escape key
    if (event.key === 'Escape') {
        closeModal();
    }
});

// Handle clicking outside the image (on the backdrop)
document.addEventListener('click', function(event) {
    const modal = document.getElementById('imageModal');
    // If the click is exactly on the modal wrapper, close it
    if (event.target === modal) {
        closeModal();
    }
});
