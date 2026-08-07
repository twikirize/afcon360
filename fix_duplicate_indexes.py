"""
AST-based fixer: remove index=True from columns that have a matching explicit Index() in __table_args__.
Handles multi-line Column definitions and qualified Index names (db.Index, etc.).
"""

import ast
from pathlib import Path

APP_DIR = Path(r"C:\Users\OBED\Desktop\afcon360_app\app")

def is_index_call(node):
    """Check if an AST node is a call to Index() or db.Index() etc."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == 'Index'
    if isinstance(func, ast.Attribute):
        return func.attr == 'Index'
    return False

def fix_model(file_path: Path) -> bool:
    content = file_path.read_text(encoding="utf-8")
    lines = content.split('\n')
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False
    
    # Find all classes and their index conflicts
    conflicts = []  # (class_name, col_name)
    
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        
        table_args_indexes = []
        column_indexes = set()
        
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        if target.id == '__table_args__':
                            if isinstance(item.value, ast.Tuple):
                                for elt in item.value.elts:
                                    if is_index_call(elt):
                                        if elt.args:
                                            cols = []
                                            for arg in elt.args[1:]:
                                                if isinstance(arg, ast.Constant):
                                                    cols.append(arg.value)
                                            for col in cols:
                                                if ',' not in col:
                                                    table_args_indexes.append(col)
                        else:
                            # Column assignment with index=True
                            if isinstance(item.value, ast.Call):
                                func = item.value.func
                                if isinstance(func, ast.Name) and func.id == 'Column':
                                    for kw in item.value.keywords:
                                        if kw.arg == 'index' and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                            column_indexes.add(target.id)
        
        for col in table_args_indexes:
            if col in column_indexes:
                conflicts.append((node.name, col))
    
    if not conflicts:
        return False
    
    # Now fix the file by removing index=True from conflicting columns
    for class_name, col_name in conflicts:
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f'{col_name} = Column(') or stripped.startswith(f'{col_name}=Column('):
                if 'index=True' in line:
                    lines[i] = line.replace(', index=True', '').replace('index=True, ', '').replace('index=True', '')
                    if lines[i].endswith(', )'):
                        lines[i] = lines[i].replace(', )', ')')
                    elif lines[i].endswith(',)'):
                        lines[i] = lines[i].replace(',)', ')')
    
    new_content = '\n'.join(lines)
    if new_content != content:
        file_path.write_text(new_content, encoding="utf-8")
        print(f"  Fixed {file_path.relative_to(APP_DIR)}: removed index=True from {len(conflicts)} columns")
        return True
    return False

def main():
    total_fixed = 0
    while True:
        fixed_this_round = 0
        for py_file in sorted(APP_DIR.rglob("*.py")):
            if "backup" in str(py_file) or "__pycache__" in str(py_file) or ".before-fix" in str(py_file):
                continue
            if fix_model(py_file):
                fixed_this_round += 1
        
        if fixed_this_round == 0:
            break
        total_fixed += fixed_this_round
        print(f"\n--- Round complete: {fixed_this_round} files fixed ---\n")
    
    print(f"\nTotal fixed: {total_fixed} model files")

if __name__ == "__main__":
    main()
