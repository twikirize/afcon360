(function(){
  'use strict';
  var root = document.getElementById('rideRequestTracker');
  if (!root) return;
  var url = root.getAttribute('data-status-url');
  var statusText = document.getElementById('requestStatusText');
  var statusMessage = document.getElementById('requestStatusMessage');
  var badge = document.getElementById('requestStatusBadge');
  var searchingEvent = document.getElementById('searchingEvent');
  var searchingEventText = document.getElementById('searchingEventText');
  var assignedEvent = document.getElementById('assignedEvent');
  var paymentStatus = document.getElementById('requestPaymentStatus');
  var cancelForm = document.getElementById('cancelRideRequestForm');

  var stopped = false;
  var pending = false;
  var timer = null;
  var timeoutTimer = null;
  var controller = null;
  var failures = 0;
  var BASE_DELAY_MS = 4000;
  var MAX_DELAY_MS = 30000;
  var REQUEST_TIMEOUT_MS = 15000;

  if (cancelForm) {
    cancelForm.addEventListener('submit', function(event){
      if (!window.confirm(
        'Cancel this ride request? If a driver has already accepted, use the trip cancellation flow instead.'
      )) event.preventDefault();
    });
  }

  function apply(data){
    if (!data) return;
    if (data.converted || data.status === 'converted') {
      stopped = true;
      if (statusText) statusText.textContent = 'Driver found';
      if (statusMessage) statusMessage.textContent = 'A driver accepted and the vehicle assignment is complete. Loading your driver and vehicle details…';
      if (searchingEvent) searchingEvent.classList.add('done');
      if (assignedEvent) assignedEvent.classList.add('done','active');
      if (paymentStatus) paymentStatus.textContent = 'Unpaid / pending — payment is due at trip completion';
      window.setTimeout(function(){ window.location.reload(); }, 700);
      return;
    }
    var cycle = data.cycle || {};
    if (data.status === 'cancelled') {
      stopped = true;
      if (statusText) statusText.textContent = 'Request cancelled';
      if (badge) badge.classList.add('terminal');
      if (statusMessage) statusMessage.textContent = 'This ride request has been cancelled. No driver or vehicle was assigned.';
      if (searchingEvent) searchingEvent.classList.remove('active');
      if (searchingEventText) searchingEventText.textContent = 'The rider cancelled this request.';
    } else if (cycle.status === 'expired' || cycle.status === 'cancelled') {
      stopped = true;
      if (statusText) statusText.textContent = cycle.status === 'cancelled' ? 'Search cancelled' : 'No driver available';
      if (badge) badge.classList.add('terminal');
      if (statusMessage) statusMessage.textContent = cycle.status === 'cancelled'
        ? 'This search cycle was cancelled.'
        : 'We could not secure a driver in this search. Your reference and search history remain available; you can try again.';
      if (searchingEvent) searchingEvent.classList.remove('active');
      if (searchingEventText) searchingEventText.textContent = 'This search cycle ended without an accepted offer.';
    } else {
      if (statusText) statusText.textContent = 'Finding your driver';
      if (badge) badge.classList.remove('terminal');
      if (statusMessage) statusMessage.textContent = 'Your request is saved. We are contacting eligible drivers. Your ride is not confirmed until a driver accepts and a vehicle is assigned.';
      if (searchingEvent) searchingEvent.classList.add('active');
    }
  }

  function schedule(delay){
    window.clearTimeout(timer);
    timer = null;
    if (!stopped && !document.hidden) {
      timer = window.setTimeout(poll, delay);
    }
  }

  function poll(){
    if (stopped || document.hidden || pending || !url) return;
    window.clearTimeout(timer);
    timer = null;
    pending = true;
    var nextDelay = BASE_DELAY_MS;
    try {
      controller = typeof AbortController !== 'undefined'
        ? new AbortController() : null;
    } catch (e) {
      controller = null;
    }
    if (controller) {
      timeoutTimer = window.setTimeout(function(){
        try { controller.abort(); } catch (e) {}
      }, REQUEST_TIMEOUT_MS);
    }

    var options = {
      credentials: 'same-origin',
      headers: {'Accept': 'application/json'}
    };
    if (controller) options.signal = controller.signal;

    fetch(url, options)
      .then(function(response){
        if (!response.ok) throw new Error('Request status unavailable');
        return response.json();
      })
      .then(function(body){
        if (!body || body.success !== true || !body.data) {
          throw new Error('Invalid request status response');
        }
        failures = 0;
        apply(body.data);
      })
      .catch(function(){
        failures += 1;
        var exponent = Math.min(failures, 3);
        nextDelay = Math.min(BASE_DELAY_MS * Math.pow(2, exponent), MAX_DELAY_MS);
        if (failures >= 3 && statusMessage && !stopped) {
          statusMessage.textContent = 'Connection issue — we will keep trying to refresh your request status.';
        }
      })
      .finally(function(){
        window.clearTimeout(timeoutTimer);
        timeoutTimer = null;
        pending = false;
        controller = null;
        if (!stopped) schedule(nextDelay);
      });
  }

  document.addEventListener('visibilitychange', function(){
    if (document.hidden) {
      window.clearTimeout(timer);
      timer = null;
      if (controller) {
        try { controller.abort(); } catch (e) {}
      }
    } else {
      poll();
    }
  });

  window.addEventListener('pagehide', function(){
    stopped = true;
    window.clearTimeout(timer);
    window.clearTimeout(timeoutTimer);
    timer = null;
    timeoutTimer = null;
    if (controller) {
      try { controller.abort(); } catch (e) {}
    }
  }, {once:true});

  poll();

})();
