// Sticky bar: show when booking form scrolls out of view
(function() {
    const bar = document.getElementById('stickyBar');
    const form = document.getElementById('booking-form') ||
                 document.querySelector('.booking-widget') ||
                 document.querySelector('form[action*="book"]');
    if (!bar || !form) return;
    const obs = new IntersectionObserver(([e]) => {
        bar.style.display = e.isIntersecting ? 'none' : 'flex';
    }, { threshold: 0.1 });
    obs.observe(form);
})();

function smoothToBooking(e) {
    e.preventDefault();
    const form = document.getElementById('booking-form') ||
                 document.querySelector('.booking-widget');
    form?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function openAllPhotos() {
    // Trigger existing modal if present, otherwise log
    const modal = document.getElementById('photoModal') ||
                  document.querySelector('.photo-modal');
    if (modal) modal.style.display = 'flex';
}