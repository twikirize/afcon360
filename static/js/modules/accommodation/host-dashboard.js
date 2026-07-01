/**
 * AFCON 360 - Accommodation Host Dashboard
 * Premium interactive features inspired by Airbnb/Booking.com
 */

(function() {
  'use strict';

  // ── Initialize on DOM ready ────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function() {
    initStatCounters();
    initListingCards();
    initBookingItems();
    initQuickActions();
  });

  // ── Animated Stat Counters ─────────────────────────────────────────
  function initStatCounters() {
    const counters = document.querySelectorAll('.stat-value-modern');
    
    counters.forEach(counter => {
      const text = counter.textContent.trim();
      const numericMatch = text.match(/[\d,]+/);
      
      if (!numericMatch) return;
      
      const target = parseInt(numericMatch[0].replace(/,/g, ''), 10);
      if (isNaN(target) || target === 0) return;
      
      const duration = 1500;
      const startTime = performance.now();

      function updateCounter(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        
        // Ease out cubic
        const easeOut = 1 - Math.pow(1 - progress, 3);
        const current = Math.floor(target * easeOut);
        
        counter.textContent = current.toLocaleString();
        
        if (progress < 1) {
          requestAnimationFrame(updateCounter);
        } else {
          counter.textContent = target.toLocaleString();
        }
      }

      // Use Intersection Observer to start animation when visible
      if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
          entries.forEach(entry => {
            if (entry.isIntersecting) {
              requestAnimationFrame(updateCounter);
              observer.unobserve(entry.target);
            }
          });
        }, { threshold: 0.5 });
        
        observer.observe(counter);
      } else {
        requestAnimationFrame(updateCounter);
      }
    });
  }

  // ── Listing Card Interactions ──────────────────────────────────────
  function initListingCards() {
    const cards = document.querySelectorAll('.listing-card-modern');
    
    cards.forEach(card => {
      // Add hover effect for image zoom
      const img = card.querySelector('.listing-image-modern img');
      if (img) {
        card.addEventListener('mouseenter', function() {
          img.style.transform = 'scale(1.08)';
        });
        card.addEventListener('mouseleave', function() {
          img.style.transform = 'scale(1)';
        });
      }

      // Quick action buttons feedback
      const buttons = card.querySelectorAll('.btn-outline-modern, .btn-primary-modern');
      buttons.forEach(btn => {
        btn.addEventListener('click', function(e) {
          // Add ripple effect
          const ripple = document.createElement('span');
          ripple.classList.add('ripple');
          this.appendChild(ripple);
          
          setTimeout(() => ripple.remove(), 600);
        });
      });
    });
  }

  // ── Booking Item Interactions ──────────────────────────────────────
  function initBookingItems() {
    const items = document.querySelectorAll('.booking-item-modern');
    
    items.forEach(item => {
      item.addEventListener('click', function(e) {
        // Don't trigger if clicking a link or button
        if (e.target.closest('a') || e.target.closest('button')) return;
        
        // Could navigate to booking detail
        const bookingId = this.getAttribute('data-booking-id');
        if (bookingId) {
          window.location.href = '/accommodation/host/bookings/' + bookingId;
        }
      });

      // Add hover cursor
      item.style.cursor = 'pointer';
    });
  }

  // ── Quick Actions ──────────────────────────────────────────────────
  function initQuickActions() {
    const actionBtns = document.querySelectorAll('.quick-action-modern');
    
    actionBtns.forEach(btn => {
      btn.addEventListener('click', function(e) {
        // Track analytics (if available)
        if (typeof gtag !== 'undefined') {
          const actionName = this.querySelector('.action-label')?.textContent || 'unknown';
          gtag('event', 'quick_action_click', {
            'action': actionName
          });
        }
      });
    });
  }

  // ── Utility: Debounce ──────────────────────────────────────────────
  function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  // ── Export for potential external use ──────────────────────────────
  window.HostDashboard = {
    animateCounter: initStatCounters
  };

})();
