from app.identity.models.organisation_provider_capability import ProviderCapabilityCode
print('Available capability codes:')
for c in ProviderCapabilityCode:
    print(f'  - {c.value}')