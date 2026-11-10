with open('templates/owner/settings.html', 'r') as f:
    content = f.read()

# Find the testOtpChannel function and its end
idx = content.find('function testOtpChannel(channel)')
if idx >= 0:
    # Find the end of the function
    brace_count = 0
    end_idx = -1
    for i in range(idx, len(content)):
        if content[i] == '{':
            brace_count += 1
        elif content[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                end_idx = i + 1
                break
    
    if end_idx > 0:
        # Add the missing functions after testOtpChannel
        new_functions = '''

async function testOciEmail() {
  const resultDiv = document.getElementById('ociTestResult');
  const btn = event.target.closest('button');
  
  resultDiv.style.display = 'block';
  resultDiv.innerHTML = '<div class="alert alert-info"><i class="bi bi-hourglass-split"></i> Sending test email...</div>';
  btn.disabled = true;
  
  try {
    const response = await fetch('{{ url_for("admin.owner.test_oci_email") }}', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
      }
    });
    
    const data = await response.json();
    
    if (data.success) {
      resultDiv.innerHTML = `<div class="alert alert-success"><i class="bi bi-check-circle"></i> ${data.message}</div>`;
    } else {
      resultDiv.innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-triangle"></i> ${data.error || 'Failed to send test email'}</div>`;
    }
  } catch (e) {
    resultDiv.innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-triangle"></i> Error: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
  }
}

async function testTwilioSms() {
  const resultDiv = document.getElementById('twilioTestResult');
  const btn = event.target.closest('button');
  
  resultDiv.style.display = 'block';
  resultDiv.innerHTML = '<div class="alert alert-info"><i class="bi bi-hourglass-split"></i> Sending test SMS...</div>';
  btn.disabled = true;
  
  try {
    const response = await fetch('{{ url_for("admin.owner.test_twilio_sms") }}', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
      }
    });
    
    const data = await response.json();
    
    if (data.success) {
      resultDiv.innerHTML = `<div class="alert alert-success"><i class="bi bi-check-circle"></i> ${data.message}</div>`;
    } else {
      resultDiv.innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-triangle"></i> ${data.error || 'Failed to send test SMS'}</div>`;
    }
  } catch (e) {
    resultDiv.innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-triangle"></i> Error: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
  }
}

async function testTwilioWhatsApp() {
  const resultDiv = document.getElementById('twilioTestResult');
  const btn = event.target.closest('button');
  
  resultDiv.style.display = 'block';
  resultDiv.innerHTML = '<div class="alert alert-info"><i class="bi bi-hourglass-split"></i> Sending test WhatsApp...</div>';
  btn.disabled = true;
  
  try {
    const response = await fetch('{{ url_for("admin.owner.test_twilio_whatsapp") }}', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
      }
    });
    
    const data = await response.json();
    
    if (data.success) {
      resultDiv.innerHTML = `<div class="alert alert-success"><i class="bi bi-check-circle"></i> ${data.message}</div>`;
    } else {
      resultDiv.innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-triangle"></i> ${data.error || 'Failed to send test WhatsApp'}</div>`;
    }
  } catch (e) {
    resultDiv.innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-triangle"></i> Error: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
  }
}
"""

        # Insert after the testOtpChannel function
        new_content = content[:end_idx] + new_functions + content[end_idx:]
        
        with open('templates/owner/settings.html', 'w') as f:
            f.write(new_content)
        print('Added missing test functions')
    else:
        print('Could not find end of testOtpChannel function')
else:
    print('Could not find testOtpChannel function')