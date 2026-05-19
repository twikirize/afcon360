import os
import re

def search_for_wallet_relationship(directory='app'):
    """Search for wallet relationship in all model files."""
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Look for relationship with 'wallet'
                    matches = re.finditer(r'(\s+wallet\s*=\s*relationship\([^)]+\))', content, re.MULTILINE)
                    for match in matches:
                        print(f"\n Found in: {filepath}")
                        print(f"   Line: {match.group(1).strip()}")
                        
                    # Also look for back_populates or backref to wallet
                    backrefs = re.finditer(r'relationship\([^)]*back_[^)]*[\'"]wallet[\'"][^)]*\)', content)
                    for match in backrefs:
                        print(f"\n Found backref to wallet in: {filepath}")
                        print(f"   Line: {match.group().strip()}")

if __name__ == '__main__':
    search_for_wallet_relationship()
    print("\n Search complete!")
