document.addEventListener('DOMContentLoaded', function() {
    'use strict';

    // Ticket selection functionality
    const ticketSelect = document.getElementById('ticket-type-select');
    const ticketInfo = document.getElementById('ticket-info');
    const totalPriceDisplay = document.getElementById('total-price-display');
    // Prefer JSON-injected data to avoid inline JS Jinja parsing issues
    const ticketTypesEl = document.getElementById('ticket-types-json');
    const currencyEl = document.getElementById('event-currency-json');
    const ticketTypes = ticketTypesEl ? JSON.parse(ticketTypesEl.textContent || '[]') : (window.ticketTypes || []);
    const currency = currencyEl ? JSON.parse(currencyEl.textContent || '""') : (window.currency || '');

    // Check if this is a free event (no paid tickets)
    const hasPaidTickets = ticketTypes.some(tt => tt.price > 0);

    const paymentSection = document.getElementById('payment-section');
    const ticketDescriptionElement = document.getElementById('ticket-description');

    // Group registration functionality
    const groupToggle = document.getElementById('group-registration-toggle');
    const groupFields = document.getElementById('group-registration-fields');
    const groupSizeSelect = document.getElementById('group-size-select');
    const additionalAttendeesContainer = document.getElementById('additional-attendees-container');

    // Group registration toggle
    if (groupToggle && groupFields) {
        groupToggle.addEventListener('change', function() {
            if (this.checked) {
                groupFields.style.display = 'block';
                updateGroupSize();
            } else {
                groupFields.style.display = 'none';
                additionalAttendeesContainer.innerHTML = '';
            }
        });
    }

    // Group size change handler
    if (groupSizeSelect) {
        groupSizeSelect.addEventListener('change', updateGroupSize);
    }

    function updateGroupSize() {
        const groupSize = parseInt(groupSizeSelect.value) || 0;
        additionalAttendeesContainer.innerHTML = '';
        
        for (let i = 1; i <= groupSize; i++) {
            addAttendeeField(i);
        }
        
        updateTotalPrice();
    }

    function addAttendeeField(attendeeNumber) {
        const attendeeDiv = document.createElement('div');
        attendeeDiv.className = 'attendee-field';
        attendeeDiv.innerHTML = `
            <div class="attendee-header">
                <h5 class="attendee-title">Additional Attendee ${attendeeNumber}</h5>
                <div class="attendee-number">${attendeeNumber}</div>
            </div>
            <div class="form-row-modern">
                <div class="form-group-modern">
                    <label class="form-label-modern">Full Name *</label>
                    <input type="text" name="attendee_${attendeeNumber}_name" class="form-control-modern" required>
                </div>
                <div class="form-group-modern">
                    <label class="form-label-modern">Email *</label>
                    <input type="email" name="attendee_${attendeeNumber}_email" class="form-control-modern" required>
                </div>
            </div>
            <div class="form-row-modern">
                <div class="form-group-modern">
                    <label class="form-label-modern">Phone</label>
                    <input type="tel" name="attendee_${attendeeNumber}_phone" class="form-control-modern">
                </div>
                <div class="form-group-modern">
                    <label class="form-label-modern">Nationality</label>
                    <input type="text" name="attendee_${attendeeNumber}_nationality" class="form-control-modern">
                </div>
            </div>
        `;
        additionalAttendeesContainer.appendChild(attendeeDiv);
    }

    function updateTotalPrice() {
        if (!hasPaidTickets) return;
        
        const selectedTicket = ticketTypes.find(tt => tt.id === parseInt(ticketSelect?.value));
        if (!selectedTicket) return;
        
        const groupSize = parseInt(groupSizeSelect?.value) || 0;
        // For paid group flows we charge for attendees only (not the payer)
        const totalTickets = (groupToggle && groupToggle.checked) ? groupSize : 1;
        const totalPrice = selectedTicket.price * totalTickets;
        
        if (totalPriceDisplay) {
            totalPriceDisplay.textContent = `${currency} ${totalPrice.toFixed(2)}`;
        }
    }

    function updatePaymentSection(selectedTicket) {
        if (!paymentSection) return;
        if (selectedTicket && selectedTicket.price > 0) {
            paymentSection.style.display = 'block';
        } else {
            paymentSection.style.display = 'none';
        }
    }

    if (ticketSelect) {
        ticketSelect.addEventListener('change', function() {
            const ticketId = parseInt(this.value);
            const selectedTicket = ticketTypes.find(tt => tt.id === ticketId);
            if (selectedTicket) {
                ticketInfo.classList.remove('d-none');
                if (ticketDescriptionElement) {
                    ticketDescriptionElement.textContent = selectedTicket.description || '';
                }
                updateTotalPrice();
                updatePaymentSection(selectedTicket);
            } else {
                ticketInfo.classList.add('d-none');
                updatePaymentSection(null);
            }
        });

        // Initialize section state based on any selected ticket
        const initialTicket = ticketTypes.find(tt => tt.id === parseInt(ticketSelect.value));
        if (initialTicket) {
            updatePaymentSection(initialTicket);
        } else {
            updatePaymentSection(null);
        }
    } else {
        updatePaymentSection(null);
    }
    
    // If the current user is already registered for this event, default to registering others
    const ctxEl = document.getElementById('event-context');
    const userRegistered = ctxEl && ctxEl.dataset && ctxEl.dataset.userRegistered === 'true';
    const bookingTypeSelect = document.getElementById('booking_type');
    const thirdPartyFields = document.getElementById('third_party_fields');
    const attendeeName = document.getElementById('attendee_name');
    const attendeeEmail = document.getElementById('attendee_email');
    if (userRegistered && bookingTypeSelect) {
        bookingTypeSelect.value = 'third_party';
        if (thirdPartyFields) thirdPartyFields.style.display = 'block';
        if (attendeeName) attendeeName.required = true;
        if (attendeeEmail) attendeeEmail.required = true;
    }

    // Form submission handler
    const registrationForm = document.getElementById('registration-form');
    if (registrationForm) {
        registrationForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            const submitBtn = document.getElementById('submit-btn');
            const originalText = submitBtn.innerHTML;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
            submitBtn.disabled = true;

            try {
                const formData = new FormData(this);
                
                // If no ticket select (free event), ensure ticket_type_id is sent as empty
                if (!document.getElementById('ticket-type-select')) {
                    formData.set('ticket_type_id', '');
                }
                
                const response = await fetch(window.location.href, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });

                const result = await response.json();

                if (result.success) {
                    window.location.href = result.redirect;
                } else {
                    alert('Error: ' + (result.error || 'Registration failed'));
                    submitBtn.innerHTML = originalText;
                    submitBtn.disabled = false;
                }

            } catch (error) {
                alert('Error: ' + error.message);
                submitBtn.innerHTML = originalText;
                submitBtn.disabled = false;
            }
        });
    }

    // Form validation enhancements
    const formControls = document.querySelectorAll('.form-control-modern');
    formControls.forEach(control => {
        control.addEventListener('blur', function() {
            if (this.hasAttribute('required') && !this.value.trim()) {
                this.classList.add('is-invalid');
            } else {
                this.classList.remove('is-invalid');
            }
        });

        control.addEventListener('focus', function() {
            this.classList.remove('is-invalid');
        });
    });

    // Email validation
    const emailInput = document.querySelector('input[type="email"]');
    if (emailInput) {
        emailInput.addEventListener('blur', function() {
            const email = this.value.trim();
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            
            if (email && !emailRegex.test(email)) {
                this.classList.add('is-invalid');
            } else {
                this.classList.remove('is-invalid');
            }
        });
    }

    // Phone number formatting
    const phoneInput = document.querySelector('input[type="tel"]');
    if (phoneInput) {
        phoneInput.addEventListener('input', function() {
            // Remove any non-digit characters except + and spaces
            this.value = this.value.replace(/[^\d\s\+]/g, '');
        });
    }

    // Add visual feedback for form submission
    const submitBtn = document.getElementById('submit-btn');
    if (submitBtn) {
        submitBtn.addEventListener('mouseenter', function() {
            if (!this.disabled) {
                this.style.transform = 'translateY(-2px)';
            }
        });

        submitBtn.addEventListener('mouseleave', function() {
            if (!this.disabled) {
                this.style.transform = 'translateY(0)';
            }
        });
    }

    // Animate form sections on scroll/load
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, observerOptions);

    // Observe form sections for animation
    document.querySelectorAll('.form-section').forEach(section => {
        section.style.opacity = '0';
        section.style.transform = 'translateY(20px)';
        section.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(section);
    });

    // Add character counter for textareas if any
    const textareas = document.querySelectorAll('textarea');
    textareas.forEach(textarea => {
        const maxLength = textarea.getAttribute('maxlength');
        if (maxLength) {
            const counter = document.createElement('small');
            counter.className = 'form-text text-muted';
            counter.textContent = `0 / ${maxLength} characters`;
            textarea.parentNode.appendChild(counter);

            textarea.addEventListener('input', function() {
                const length = this.value.length;
                counter.textContent = `${length} / ${maxLength} characters`;
                
                if (length > maxLength * 0.9) {
                    counter.classList.add('text-warning');
                } else {
                    counter.classList.remove('text-warning');
                }
            });
        }
    });

    // Add confirmation for form exit if data is entered
    let formModified = false;
    const inputs = registrationForm ? registrationForm.querySelectorAll('input, select, textarea') : [];
    
    inputs.forEach(input => {
        input.addEventListener('change', () => {
            formModified = true;
        });
    });

    // Show confirmation before leaving if form is modified
    window.addEventListener('beforeunload', (e) => {
        if (formModified) {
            e.preventDefault();
            e.returnValue = '';
        }
    });

    // Reset form modified flag on successful submission
    if (registrationForm) {
        registrationForm.addEventListener('submit', () => {
            formModified = false;
        });
    }
});
