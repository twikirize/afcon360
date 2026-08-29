# Fix indentation in the kyc_limit_service.py file
with open(r'C:\Users\OBED\Desktop\afcon360_app\app\wallet\services\kyc_limit_service.py', 'r') as f:
    content = f.read()

# Fix the duplicate code issue
content = content.replace(
    """        return None
            if op is None:
                return regulatory
            return min(regulatory, Decimal(str(op)))
        if period == 'monthly':
            regulatory = reg.get('monthly_limit') or Decimal('0')
            if not regulatory:
                return None
            return regulatory
        return None

    @classmethod
    def enforce_cumulative_volume(""",
    """        return None

    @classmethod
    def enforce_cumulative_volume("""
)

# Fix the @classmethod decorator indentation for _get_effective_cumulative_limit
content = content.replace(
    """@classmethod
    def _get_effective_cumulative_limit(""",
    """    @classmethod
    def _get_effective_cumulative_limit("""
)

# Fix the enforce_cumulative_volume decorator
content = content.replace(
    """    @classmethod
    def enforce_cumulative_volume(""",
    """    @classmethod
    def enforce_cumulative_volume("""
)

with open(r'C:\Users\OBED\Desktop\afcon360_app\app\wallet\services\kyc_limit_service.py', 'w') as f:
    f.write(content)

print('Fixed indentation')