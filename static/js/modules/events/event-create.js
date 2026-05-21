document.addEventListener('DOMContentLoaded', function(){
  'use strict';

  /* ── CSRF ── */
  function getCSRF(){
    const m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : '';
  }

  /* ── EVENT TYPE TOGGLE ── */
  const radios = document.querySelectorAll('input[name="event_type"]');
  const ticketedFields = document.getElementById('ticketed-fields');

  function updateTicketingVisibility(){
    const isTicketed = document.querySelector('input[name="event_type"]:checked').value === 'ticketed';
    if(isTicketed) {
      ticketedFields.classList.add('show');
      ticketedFields.classList.remove('d-none');
      if(document.querySelectorAll('.ticket-row').length === 0) addTierRow();
    } else {
      ticketedFields.classList.remove('show');
      ticketedFields.classList.add('d-none');
    }
  }

  radios.forEach(r => r.addEventListener('change', updateTicketingVisibility));
  
  // Initialize visibility on page load
  updateTicketingVisibility();

  /* ── TIER ROWS ── */
  function addTierRow(name='', price='', capacity='', template='custom'){
    const row = document.createElement('div');
    row.className = 'ticket-row-enhanced';
    
    const templateData = getTierTemplate(template);
    const benefits = templateData.benefits || [];
    
    row.innerHTML = `
      <div class="ticket-row-enhanced-grid">
        <div class="form-group-modern">
          <input type="text" name="tier_name[]" class="form-control-modern" placeholder="Tier Name (e.g. VIP)" value="${name || templateData.name}" required>
          <textarea name="tier_description[]" class="form-control-modern" placeholder="Description (optional)" rows="2">${templateData.description || ''}</textarea>
        </div>
        <div class="form-group-modern">
          <input type="number" name="tier_price[]" class="form-control-modern" placeholder="Price" step="0.01" value="${price || templateData.price}" min="0" required>
          <div class="form-help-text">Set 0 for free tier</div>
        </div>
        <div class="form-group-modern">
          <input type="number" name="tier_capacity[]" class="form-control-modern" placeholder="Capacity" value="${capacity || templateData.capacity}" min="0">
          <div class="form-help-text">0 for unlimited</div>
        </div>
        <div class="form-group-modern">
          <label class="form-label-modern">Available From</label>
          <input type="datetime-local" name="tier_available_from[]" class="form-control-modern" value="${templateData.available_from || ''}">
        </div>
        <button type="button" class="btn-remove-tier"><i class="fas fa-times"></i></button>
      </div>
      
      <div class="ticket-advanced-options">
        <div class="form-group-modern">
          <label class="form-label-modern">Available Until</label>
          <input type="datetime-local" name="tier_available_until[]" class="form-control-modern" value="${templateData.available_until || ''}">
        </div>
        <div class="form-group-modern">
          <label class="form-label-modern">Min Purchase</label>
          <input type="number" name="tier_min_purchase[]" class="form-control-modern" placeholder="1" value="${templateData.min_purchase || 1}" min="1">
        </div>
      </div>
      
      <div class="ticket-benefits">
        <label class="form-label-modern">Benefits (optional)</label>
        <div class="benefits-list">
          ${benefits.map((benefit, index) => `
            <div class="benefit-item">
              <input type="checkbox" name="tier_benefits_${Date.now()}[]" value="${benefit}" ${templateData.defaultBenefits?.includes(benefit) ? 'checked' : ''}>
              <span>${benefit}</span>
            </div>
          `).join('')}
          <div class="benefit-item">
            <input type="text" name="tier_custom_benefit_${Date.now()}[]" placeholder="Add custom benefit" class="form-control-modern">
          </div>
        </div>
      </div>
    `;
    
    document.getElementById('ticket-rows').appendChild(row);
    
    // Add event listeners for dynamic benefit management
    setupBenefitManagement(row);
  }
  
  function getTierTemplate(template) {
    const templates = {
      early_bird: {
        name: 'Early Bird',
        description: 'Special early bird pricing',
        price: '50',
        capacity: '100',
        available_from: '',
        available_until: '',
        min_purchase: 1,
        benefits: ['Early access', 'Priority seating', 'Special badge'],
        defaultBenefits: ['Early access', 'Priority seating']
      },
      standard: {
        name: 'Standard',
        description: 'Standard admission',
        price: '75',
        capacity: '500',
        available_from: '',
        available_until: '',
        min_purchase: 1,
        benefits: ['General admission', 'Standard seating'],
        defaultBenefits: ['General admission']
      },
      vip: {
        name: 'VIP',
        description: 'Premium VIP experience',
        price: '150',
        capacity: '50',
        available_from: '',
        available_until: '',
        min_purchase: 1,
        benefits: ['VIP seating', 'Complimentary drinks', 'Meet & greet', 'Priority entry', 'Exclusive merchandise'],
        defaultBenefits: ['VIP seating', 'Complimentary drinks', 'Meet & greet']
      },
      group: {
        name: 'Group Package',
        description: 'Special group pricing',
        price: '250',
        capacity: '20',
        available_from: '',
        available_until: '',
        min_purchase: 5,
        benefits: ['Group discount', 'Reserved seating', 'Group coordinator benefits'],
        defaultBenefits: ['Group discount', 'Reserved seating']
      }
    };
    
    return templates[template] || { name: '', description: '', price: '', capacity: '', benefits: [] };
  }
  
  function setupBenefitManagement(row) {
    // Add dynamic benefit addition/removal
    const benefitsList = row.querySelector('.benefits-list');
    if (benefitsList) {
      benefitsList.addEventListener('click', function(e) {
        if (e.target.type === 'text' && e.target.value && e.key === 'Enter') {
          e.preventDefault();
          const newBenefit = document.createElement('div');
          newBenefit.className = 'benefit-item';
          newBenefit.innerHTML = `
            <input type="checkbox" name="tier_benefits_${Date.now()}[]" value="${e.target.value}" checked>
            <span>${e.target.value}</span>
          `;
          e.target.parentNode.replaceChild(newBenefit, e.target);
        }
      });
    }
  }

  document.getElementById('add-tier-btn').addEventListener('click', () => addTierRow());

  // Tier template buttons
  document.querySelectorAll('.btn-template').forEach(btn => {
    btn.addEventListener('click', function() {
      const template = this.dataset.template;
      addTierRow('', '', '', template);
    });
  });

  // Load available payment methods
  loadAvailablePaymentMethods();

  async function loadAvailablePaymentMethods() {
    const loadingDiv = document.getElementById('payment-methods-loading');
    const containerDiv = document.getElementById('payment-methods-container');
    
    try {
      // Get available payment methods for all currencies (admin config)
      const response = await fetch('/admin/api/payment-methods');
      const data = await response.json();
      
      if (data.success) {
        renderPaymentMethodsForEventCreation(data.payment_methods);
        loadingDiv.style.display = 'none';
        containerDiv.style.display = 'grid';
      } else {
        loadingDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error loading payment methods';
      }
    } catch (error) {
      loadingDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Network error';
    }
  }

  function renderPaymentMethodsForEventCreation(paymentMethods) {
    const container = document.getElementById('payment-methods-container');
    container.innerHTML = '';
    
    // Filter to only show available methods
    const availableMethods = paymentMethods.filter(method => method.is_available);
    
    availableMethods.forEach(method => {
      const methodDiv = document.createElement('div');
      methodDiv.className = 'payment-method-option';
      
      methodDiv.innerHTML = `
        <label class="payment-method-label">
          <input type="checkbox" name="payment_methods[]" value="${method.method_id}" ${method.method_id === 'wallet' ? 'checked' : ''}>
          <span class="payment-method-icon">${method.icon}</span>
          <span>${method.name}</span>
        </label>
      `;
      
      container.appendChild(methodDiv);
    });
    
    // Add info about disabled methods
    const disabledMethods = paymentMethods.filter(method => !method.is_available);
    if (disabledMethods.length > 0) {
      const infoDiv = document.createElement('div');
      infoDiv.className = 'form-help-text';
      infoDiv.style.marginTop = '1rem';
      infoDiv.innerHTML = `<i class="fas fa-info-circle"></i> ${disabledMethods.length} payment method(s) disabled by administrator. Contact admin to enable: ${disabledMethods.map(m => m.name).join(', ')}`;
      container.appendChild(infoDiv);
    }
  }

  document.getElementById('ticket-rows').addEventListener('click', function(e){
    const btn = e.target.closest('.btn-remove-tier');
    if(!btn) return;
    const rows = this.querySelectorAll('.ticket-row-enhanced');
    if(rows.length > 1){
      btn.closest('.ticket-row-enhanced').remove();
    } else {
      btn.closest('.ticket-row-enhanced').querySelectorAll('input, textarea').forEach(i => i.value = '');
    }
  });

  /* ── DATE SETUP ── */
  const today = new Date().toISOString().split('T')[0];
  const startInput = document.getElementById('start_date');
  const endInput   = document.getElementById('end_date');
  startInput.setAttribute('min', today);
  startInput.addEventListener('change', function(){
    if(this.value){
      endInput.setAttribute('min', this.value);
    } else {
      endInput.removeAttribute('min');
    }
    if(endInput.value && endInput.value < this.value) endInput.value = '';
  });

  /* ── VALIDATION ── */
  function showError(msg){
    alert(msg);
  }
  function clearError(){
    // no-op
  }

  function markInvalid(name){
    var el = document.querySelector('[name="' + name + '"]');
    if(el){ el.classList.add('invalid'); el.focus(); }
  }

  function validate(data){
    if(!data.name || !data.name.trim()){
      markInvalid('name'); return 'Event name is required.';
    }
    if(data.name.trim().length < 3){
      markInvalid('name'); return 'Event name must be at least 3 characters.';
    }
    if(!data.city || !data.city.trim()){
      markInvalid('city'); return 'City is required.';
    }
    if(!data.start_date){
      markInvalid('start_date'); return 'Start date is required.';
    }
    if(data.start_date < today){
      markInvalid('start_date'); return 'Start date cannot be in the past.';
    }
    if(data.end_date && data.end_date < data.start_date){
      markInvalid('end_date'); return 'End date must be on or after the start date.';
    }
    if(data.event_type === 'ticketed'){
      // Validate currency
      if(!data.currency){
        markInvalid('currency'); return 'Currency is required for ticketed events.';
      }
      
      // Validate payment methods
      if(!data.payment_methods || data.payment_methods.length === 0){
        return 'Please select at least one payment method.';
      }
      
      // Validate ticket tiers
      var tiers = data.ticket_tiers || [];
      if(!tiers.length || !tiers[0].name){
        return 'Please add at least one ticket tier with a name.';
      }
      for(var i=0; i<tiers.length; i++){
        if(tiers[i].price < 0){ return 'Ticket price cannot be negative.'; }
        if(tiers[i].capacity < 0){ return 'Ticket capacity cannot be negative.'; }
        if(tiers[i].min_purchase < 1){ return 'Minimum purchase must be at least 1.'; }
        
        // Validate date ranges
        if(tiers[i].available_from && tiers[i].available_until && 
           tiers[i].available_from >= tiers[i].available_until){
          return 'Available from date must be before available until date.';
        }
      }
    }
    if(data.contact_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.contact_email)){
      markInvalid('contact_email'); return 'Please enter a valid contact email.';
    }
    if(data.website && !/^https?:\/\/.+/.test(data.website)){
      markInvalid('website'); return 'Website must start with http:// or https://';
    }
    return null;
  }

  /* ── SUBMIT — intercept form submission ── */
  document.getElementById('event-form').addEventListener('submit', async function(e){
    e.preventDefault();
    clearError();

    var form = this;
    form.querySelectorAll('.invalid').forEach(function(el){ el.classList.remove('invalid'); });

    var formData = new FormData(form);
    var data = {};

    ['name','description','category','city','venue','start_date','end_date',
     'event_type','website','contact_email','currency'].forEach(function(k){
      data[k] = (formData.get(k) || '').trim();
    });

    data.registration_required = true;

    // Payment methods
    data.payment_methods = formData.getAll('payment_methods[]');

    // Enhanced ticket tiers
    if(data.event_type === 'ticketed'){
      var tierNames        = formData.getAll('tier_name[]');
      var tierDescriptions = formData.getAll('tier_description[]');
      var tierPrices       = formData.getAll('tier_price[]');
      var tierCaps         = formData.getAll('tier_capacity[]');
      var tierAvailFrom    = formData.getAll('tier_available_from[]');
      var tierAvailUntil   = formData.getAll('tier_available_until[]');
      var tierMinPurchase  = formData.getAll('tier_min_purchase[]');
      
      data.ticket_tiers = tierNames
        .map(function(n, i){
          var tier = {
            name:             n.trim(),
            description:      (tierDescriptions[i] || '').trim(),
            price:            parseFloat(tierPrices[i]) || 0,
            capacity:         tierCaps[i] ? parseInt(tierCaps[i]) : null,
            available_from:   tierAvailFrom[i] || null,
            available_until:  tierAvailUntil[i] || null,
            min_purchase:     tierMinPurchase[i] ? parseInt(tierMinPurchase[i]) : 1,
            benefits:         []
          };
          
          // Collect benefits for this tier
          var benefitInputs = document.querySelectorAll(`input[name^="tier_benefits_"]:checked`);
          benefitInputs.forEach(function(input) {
            if (input.value && tier.name === getTierNameForBenefit(input)) {
              tier.benefits.push(input.value);
            }
          });
          
          return tier;
        })
        .filter(function(t){ return t.name; });
    }
    
    function getTierNameForBenefit(input) {
      var tierRow = input.closest('.ticket-row-enhanced');
      if (tierRow) {
        var nameInput = tierRow.querySelector('input[name="tier_name[]"]');
        return nameInput ? nameInput.value.trim() : '';
      }
      return '';
    }

    // Validate
    var err = validate(data);
    if(err){ showError(err); return; }

    // Submit
    var btn = document.getElementById('submit-btn');
    var orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating\u2026';

    try {
      var res = await fetch("/events/create", {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRF()
        },
        body: JSON.stringify(data)
      });

      var result = await res.json();

      if(result.success && result.redirect){
        window.location.href = result.redirect;
      } else {
        showError(result.error || 'Something went wrong. Please try again.');
        btn.disabled = false;
        btn.innerHTML = orig;
      }
    } catch(fetchErr){
      showError('Network error — please check your connection and try again.');
      btn.disabled = false;
      btn.innerHTML = orig;
    }
  });

});
