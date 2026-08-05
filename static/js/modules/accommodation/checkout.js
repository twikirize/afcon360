/* ============================================================ */
/* CHECKOUT PAGE - INTERACTIVE LOGIC                             */
/* ============================================================ */

(function() {
    let currentStep = 1;
    let groupBookingId = null;

    function showStep(step) {
        document.querySelectorAll('.wizard-step').forEach(function(el) {
            el.classList.remove('active');
        });
        var targetStep = document.getElementById('step' + step);
        if (targetStep) {
            targetStep.classList.add('active');
        }

        document.querySelectorAll('.step-indicator .step').forEach(function(el) {
            el.classList.remove('active');
        });
        var indicatorStep = document.querySelector('.step-indicator .step[data-step="' + step + '"]');
        if (indicatorStep) {
            indicatorStep.classList.add('active');
        }

        document.querySelectorAll('.step-indicator .step').forEach(function(el) {
            var s = parseInt(el.dataset.step);
            if (s < step) el.classList.add('completed');
            else el.classList.remove('completed');
        });
        currentStep = step;
        sessionStorage.setItem('checkoutWizardStep', step);
    }

    function nextStep(step) {
        showStep(step);
    }

    function prevStep(step) {
        showStep(step);
    }

    function validateAndNext(fromStep, toStep) {
        var error = false;
        var timingSelected = document.querySelector('[name="payment_timing"]:checked');
        if (!timingSelected) {
            var feedback = document.getElementById('payment-timing-feedback');
            if (feedback) feedback.classList.add('show');
            error = true;
        } else {
            var feedback = document.getElementById('payment-timing-feedback');
            if (feedback) feedback.classList.remove('show');
        }

        var methodSelected = document.querySelector('[name="payment_method"]:checked');
        if (!methodSelected) {
            var feedback = document.getElementById('payment-method-feedback');
            if (feedback) feedback.classList.add('show');
            error = true;
        } else {
            var feedback = document.getElementById('payment-method-feedback');
            if (feedback) feedback.classList.remove('show');
        }

        if (error) {
            var first = document.querySelector('.checkout-feedback.show');
            if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }
        showStep(toStep);
    }

    function selectBookingType(type) {
        var selfRadio = document.getElementById('bookingSelf');
        var thirdPartyRadio = document.getElementById('bookingThirdParty');
        var groupRadio = document.getElementById('bookingGroup');

        if (selfRadio) selfRadio.checked = (type === 'self');
        if (thirdPartyRadio) thirdPartyRadio.checked = (type === 'third_party');
        if (groupRadio) groupRadio.checked = (type === 'group');

        document.querySelectorAll('.booking-type-card').forEach(function(card) {
            card.classList.toggle('selected', card.querySelector('input[type="radio"]')?.checked);
        });

        var thirdPartySection = document.getElementById('thirdPartySection');
        var groupSection = document.getElementById('groupSection');

        if (thirdPartySection) {
            thirdPartySection.style.display = type === 'third_party' ? 'block' : 'none';
        }
        if (groupSection) {
            groupSection.style.display = type === 'group' ? 'block' : 'none';
        }

        if (type === 'group' && !groupBookingId) {
            groupBookingId = 'group_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            var groupBookingIdEl = document.getElementById('groupBookingId');
            if (groupBookingIdEl) {
                groupBookingIdEl.value = groupBookingId;
            }
        }
    }

    function selectPaymentMethod(methodId) {
        var wasAlreadySelected = document.querySelector('[name="payment_method"][value="' + methodId + '"]')?.checked;

        document.querySelectorAll('[name="payment_method"]').forEach(function(el) {
            el.checked = false;
        });
        document.querySelectorAll('.payment-method-card').forEach(function(card) {
            card.classList.remove('selected');
        });

        if (!wasAlreadySelected) {
            var radio = document.querySelector('[name="payment_method"][value="' + methodId + '"]');
            if (radio) {
                radio.checked = true;
                radio.closest('.payment-method-card')?.classList.add('selected');
            }

            var labels = {
                'wallet': 'Paid from your AFCON360 wallet',
                'cash': 'Pay with cash on arrival'
            };
            var labelEl = document.getElementById('payment-method-label');
            if (labelEl && labels[methodId]) {
                labelEl.innerHTML = '<i class="fas fa-info-circle"></i> ' + labels[methodId];
            }
        } else {
            var labelEl = document.getElementById('payment-method-label');
            if (labelEl) {
                labelEl.innerHTML = '<i class="fas fa-info-circle"></i> Select a payment method';
            }
        }

        var feedback = document.getElementById('payment-method-feedback');
        if (feedback) {
            feedback.classList.remove('show');
        }
    }

    function selectTiming(timing) {
        var wasAlreadySelected = document.querySelector('[name="payment_timing"]:checked')?.value === timing;

        document.querySelectorAll('[name="payment_timing"]').forEach(function(el) {
            el.checked = false;
        });
        document.querySelectorAll('.timing-card').forEach(function(card) {
            card.classList.remove('selected');
        });

        if (!wasAlreadySelected) {
            var radio = document.querySelector('[name="payment_timing"][value="' + timing + '"]');
            if (radio) {
                radio.checked = true;
                radio.closest('.timing-card')?.classList.add('selected');
            }

            var depositSection = document.getElementById('depositSection');
            if (depositSection) {
                depositSection.style.display = timing === 'deposit' ? 'block' : 'none';
            }

            var methodWrappers = document.querySelectorAll('.payment-method-wrapper');
            var methodRadios = document.querySelectorAll('[name="payment_method"]');

            methodWrappers.forEach(function(wrapper) { wrapper.style.display = 'block'; });
            methodRadios.forEach(function(radio) { radio.checked = false; });

            var firstVisible = null;
            var hasVisible = false;

            methodWrappers.forEach(function(wrapper) {
                var allowedTimings = wrapper.dataset.timing ? wrapper.dataset.timing.split(',') : [];
                var isVisible = allowedTimings.includes(timing) || allowedTimings.includes('all');

                if (!isVisible) {
                    wrapper.style.display = 'none';
                } else {
                    hasVisible = true;
                    if (!firstVisible) {
                        firstVisible = wrapper.querySelector('[name="payment_method"]');
                    }
                }
            });

            if (firstVisible) {
                selectPaymentMethod(firstVisible.value);
            }

            var container = document.getElementById('paymentMethodsContainer');
            var noMethodsMsg = document.getElementById('noPaymentMethodsMsg');

            if (!hasVisible) {
                if (!noMethodsMsg) {
                    var msg = document.createElement('div');
                    msg.id = 'noPaymentMethodsMsg';
                    msg.className = 'alert alert-warning mt-2';
                    msg.textContent = 'No payment methods available for this option. Please select a different payment timing.';
                    container.appendChild(msg);
                }
            } else if (noMethodsMsg) {
                noMethodsMsg.remove();
            }

            var summaryText = document.getElementById('payment-summary-text');
            var totalEl = document.getElementById('bookingTotal');
            var total = totalEl ? parseFloat(totalEl.dataset.value || totalEl.textContent) : 0;
            var currency = '$';

            if (summaryText) {
                switch(timing) {
                    case 'pay_now':
                        summaryText.textContent = 'You will be charged ' + currency + total.toFixed(2) + ' now. Booking confirmed immediately.';
                        break;
                    case 'deposit':
                        var depositPct = parseFloat(document.querySelector('[name="deposit_percentage"]')?.value || 0);
                        var depositAmount = total * (depositPct / 100);
                        summaryText.textContent = 'You will be charged ' + currency + depositAmount.toFixed(2) + ' now (' + depositPct + '% deposit). Balance of ' + currency + (total - depositAmount).toFixed(2) + ' due before check-in.';
                        break;
                    case 'pay_on_arrival':
                        summaryText.textContent = 'No payment now. You\'ll pay ' + currency + total.toFixed(2) + ' when you check in. Booking requires host approval.';
                        break;
                    case 'invoice':
                        summaryText.textContent = 'We\'ll send you an invoice for ' + currency + total.toFixed(2) + '. Payment due in 30 days.';
                        break;
                    default:
                        summaryText.textContent = 'You will be charged ' + currency + total.toFixed(2) + ' now.';
                }
            }

            var submitBtn = document.getElementById('submit-btn');
            var timingLabels = {
                'pay_now': 'Pay Now',
                'deposit': 'Pay Deposit',
                'pay_on_arrival': 'Book Now',
                'invoice': 'Request Invoice'
            };
            var icons = {
                'pay_now': 'fa-credit-card',
                'deposit': 'fa-hand-holding-usd',
                'pay_on_arrival': 'fa-hotel',
                'invoice': 'fa-file-invoice'
            };
            if (submitBtn) {
                submitBtn.innerHTML = '<i class="fas ' + icons[timing] + ' me-1"></i> ' + timingLabels[timing];
            }
        } else {
            var depositSection = document.getElementById('depositSection');
            if (depositSection) {
                depositSection.style.display = 'none';
            }
            document.querySelectorAll('.payment-method-wrapper').forEach(function(wrapper) { wrapper.style.display = 'block'; });
            document.querySelectorAll('[name="payment_method"]').forEach(function(radio) { radio.checked = false; });
            document.querySelectorAll('.payment-method-card').forEach(function(card) { card.classList.remove('selected'); });

            var summaryText = document.getElementById('payment-summary-text');
            if (summaryText) {
                summaryText.textContent = 'Please select a payment option above.';
            }
            var submitBtn = document.getElementById('submit-btn');
            if (submitBtn) {
                submitBtn.innerHTML = '<i class="fas fa-credit-card me-1"></i> Confirm Booking';
            }

            var labelEl = document.getElementById('payment-method-label');
            if (labelEl) {
                labelEl.innerHTML = '<i class="fas fa-info-circle"></i> Select a payment method';
            }
        }

        var timingFeedback = document.getElementById('payment-timing-feedback');
        if (timingFeedback) {
            timingFeedback.classList.remove('show');
        }
    }

    // ---- Event delegation: wizard navigation ----
    document.addEventListener('click', function(event) {
        var btn = event.target.closest('.btn-wizard');
        if (!btn) return;

        var nextStepVal = btn.dataset.nextStep;
        var prevStepVal = btn.dataset.prevStep;

        if (nextStepVal !== undefined) {
            var targetStep = parseInt(nextStepVal, 10);
            if (btn.dataset.validate !== undefined) {
                validateAndNext(currentStep, targetStep);
            } else {
                nextStep(targetStep);
            }
        }

        if (prevStepVal !== undefined) {
            prevStep(parseInt(prevStepVal, 10));
        }
    });

    // ---- Event delegation: booking type cards ----
    document.addEventListener('click', function(event) {
        var bookingCard = event.target.closest('.booking-type-card');
        if (bookingCard) {
            var bookingType = bookingCard.dataset.bookingType;
            if (bookingType) {
                selectBookingType(bookingType);
            }
        }
    });

    // ---- Event delegation: payment method cards ----
    document.addEventListener('click', function(event) {
        var paymentCard = event.target.closest('.payment-method-card');
        if (paymentCard) {
            var methodId = paymentCard.dataset.methodId;
            if (methodId) {
                selectPaymentMethod(methodId);
            }
        }
    });

    // ---- Event delegation: timing cards ----
    document.addEventListener('click', function(event) {
        var timingCard = event.target.closest('.timing-card');
        if (timingCard) {
            var timingValue = timingCard.dataset.timingValue;
            if (timingValue) {
                selectTiming(timingValue);
            }
        }
    });

    // ---- Additional event listeners ----
    document.querySelector('[name="deposit_percentage"]')?.addEventListener('change', function() {
        var selectedTiming = document.querySelector('[name="payment_timing"]:checked');
        if (selectedTiming && selectedTiming.value === 'deposit') {
            selectTiming('deposit');
        }
    });

    document.getElementById('checkout-form')?.addEventListener('submit', function(e) {
        if (!document.getElementById('terms').checked) {
            e.preventDefault();
            alert('Please accept the terms and conditions.');
            return false;
        }
        if (!document.querySelector('[name="payment_timing"]:checked') || !document.querySelector('[name="payment_method"]:checked')) {
            e.preventDefault();
            alert('Please complete the payment selection before confirming.');
            return false;
        }

        var btn = document.getElementById('submit-btn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';
        }

        sessionStorage.removeItem('checkoutWizardStep');

        return true;
    });

    document.querySelector('[name="num_guests"]')?.addEventListener('change', function() {
        var guestCountDisplay = document.getElementById('guestCountDisplay');
        if (guestCountDisplay) {
            guestCountDisplay.innerText = this.value;
        }
    });

    document.getElementById('totalRooms')?.addEventListener('change', function() {
        var roomNumberInput = document.getElementById('roomNumber');
        if (roomNumberInput) {
            var currentRoom = parseInt(roomNumberInput.value);
            var totalRooms = parseInt(this.value);

            if (currentRoom > totalRooms) {
                roomNumberInput.value = totalRooms;
            }
            roomNumberInput.max = totalRooms;
            roomNumberInput.readOnly = false;
        }
    });

    // ---- Initialise ----
    document.addEventListener('DOMContentLoaded', function() {
        var savedStep = sessionStorage.getItem('checkoutWizardStep');
        if (savedStep) {
            showStep(parseInt(savedStep, 10));
        } else {
            showStep(1);
        }

        var selectedTiming = document.querySelector('[name="payment_timing"]:checked');
        if (selectedTiming) {
            var depositSection = document.getElementById('depositSection');
            if (depositSection) {
                depositSection.style.display = selectedTiming.value === 'deposit' ? 'block' : 'none';
            }
            selectTiming(selectedTiming.value);
        }
        var firstPayment = document.querySelector('[name="payment_method"]');
        if (firstPayment) {
            selectPaymentMethod(firstPayment.value);
        }
        var firstBooking = document.querySelector('[name="booking_type"]');
        if (firstBooking && !document.querySelector('[name="booking_type"]:checked')) {
            selectBookingType('self');
        }
    });
})();