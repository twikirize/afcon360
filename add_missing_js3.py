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
        new_functions = "\n\nasync function testOciEmail() {\n  const resultDiv = document.getElementById('ociTestResult');\n  const btn = event.target.closest('button');\n  \n  resultDiv.style.display = 'block';\n  resultDiv.innerHTML = '<div class=\"alert alert-info\"><i class=\"bi bi-hourglass-split\"></i> Sending test email...</div>';\n  btn.disabled = true;\n  \n  try {\n    const response = await fetch('{{ url_for(\"admin.owner.test_oci_email\") }}', {\n      method: 'POST',\n      headers: {\n        'Content-Type': 'application/json',\n        'X-CSRFToken': document.querySelector('meta[name=\"csrf-token\"]').content\n      }\n    });\n    \n    const data = await response.json();\n    \n    if (data.success) {\n      resultDiv.innerHTML = `<div class=\"alert alert-success\"><i class=\"bi bi-check-circle\"></i> ${data.message}</div>`;\n    } else {\n      resultDiv.innerHTML = `<div class=\"alert alert-danger\"><i class=\"bi bi-exclamation-triangle\"></i> ${data.error || \"Failed to send test email\"}</div>`;\n    }\n  } catch (e) {\n    resultDiv.innerHTML = `<div class=\"alert alert-danger\"><i class=\"bi bi-exclamation-triangle\"></i> Error: ${e.message}</div>`;\n  } finally {\n    btn.disabled = false;\n  }\n}\n\nasync function testTwilioSms() {\n  const resultDiv = document.getElementById('twilioTestResult');\n  const btn = event.target.closest('button');\n  \n  resultDiv.style.display = 'block';\n  resultDiv.innerHTML = '<div class=\"alert alert-info\"><i class=\"bi bi-hourglass-split\"></i> Sending test SMS...</div>';\n  btn.disabled = true;\n  \n  try {\n    const response = await fetch('{{ url_for(\"admin.owner.test_twilio_sms\") }}', {\n      method: 'POST',\n      headers: {\n        'Content-Type': 'application/json',\n        'X-CSRFToken': document.querySelector('meta[name=\"csrf-token\"]').content\n      }\n    });\n    \n    const data = await response.json();\n    \n    if (data.success) {\n      resultDiv.innerHTML = `<div class=\"alert alert-success\"><i class=\"bi bi-check-circle\"></i> ${data.message}</div>`;\n    } else {\n      resultDiv.innerHTML = `<div class=\"alert alert-danger\"><i class=\"bi bi-exclamation-triangle\"></i> ${data.error || \"Failed to send test SMS\"}</div>`;\n    }\n  } catch (e) {\n    resultDiv.innerHTML = `<div class=\"alert alert-danger\"><i class=\"bi bi-exclamation-triangle\"></i> Error: ${e.message}</div>`;\n  } finally {\n    btn.disabled = false;\n  }\n}\n\nasync function testTwilioWhatsApp() {\n  const resultDiv = document.getElementById('twilioTestResult');\n  const btn = event.target.closest('button');\n  \n  resultDiv.style.display = 'block';\n  resultDiv.innerHTML = '<div class=\"alert alert-info\"><i class=\"bi bi-hourglass-split\"></i> Sending test WhatsApp...</div>';\n  btn.disabled = true;\n  \n  try {\n    const response = await fetch('{{ url_for(\"admin.owner.test_twilio_whatsapp\") }}', {\n      method: 'POST',\n      headers: {\n        'Content-Type': 'application/json',\n        'X-CSRFToken': document.querySelector('meta[name=\"csrf-token\"]').content\n      }\n    });\n    \n    const data = await response.json();\n    \n    if (data.success) {\n      resultDiv.innerHTML = `<div class=\"alert alert-success\"><i class=\"bi bi-check-circle\"></i> ${data.message}</div>`;\n    } else {\n      resultDiv.innerHTML = `<div class=\"alert alert-danger\"><i class=\"bi bi-exclamation-triangle\"></i> ${data.error || \"Failed to send test WhatsApp\"}</div>`;\n    }\n  } catch (e) {\n    resultDiv.innerHTML = `<div class=\"alert alert-danger\"><i class=\"bi bi-exclamation-triangle\"></i> Error: ${e.message}</div>`;\n  } finally {\n    btn.disabled = false;\n  }\n}\n"
        
        # Insert after the testOtpChannel function
        new_content = content[:end_idx] + new_functions + content[end_idx:]
        
        with open('templates/owner/settings.html', 'w') as f:
            f.write(new_content)
        print('Added missing test functions')
    else:
        print('Could not find end of testOtpChannel function')
else:
    print('Could not find testOtpChannel function')