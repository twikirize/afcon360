"""
Use AST parsing to find all models with duplicate index definitions.
This handles multi-line Column definitions properly.
"""

import ast
from pathlib import Path

APP_DIR = Path(r"C:\Users\OBED\Desktop\afcon360_app\app")

def find_duplicate_indexes(file_path: Path):
    """Find models where a column has index=True and there's also an explicit Index() in __table_args__."""
    content = file_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    
    duplicates = []
    
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        
        # Find __table_args__ assignment
        table_args_indexes = []
        column_indexes = {}
        
        for item in node.body:
            # Find __table_args__ = (Index(...), ...)
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == '__table_args__':
                        # Parse the tuple of Index() calls
                        if isinstance(item.value, ast.Tuple):
                            for elt in item.value.elts:
                                if isinstance(elt, ast.Call):
                                    func = elt.func
                                    if isinstance(func, ast.Name) and func.id == 'Index':
                                        # Get index name and column names
                                        if elt.args:
                                            idx_name = None
                                            cols = []
                                            if isinstance(elt.args[0], ast.Constant):
                                                idx_name = elt.args[0].value
                                            for arg in elt.args[1:]:
                                                if isinstance(arg, ast.Constant):
                                                    cols.append(arg.value)
                                            if idx_name and cols:
                                                table_args_indexes.append((idx_name, cols))
            
            # Find Column(..., index=True) assignments
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        col_name = target.id
                        if isinstance(item.value, ast.Call):
                            func = item.value.func
                            if isinstance(func, ast.Name) and func.id == 'Column':
                                # Check for index=True keyword arg
                                for kw in item.value.keywords:
                                    if kw.arg == 'index' and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                        column_indexes[col_name] = True
        
        # Check for conflicts
        for idx_name, cols in table_args_indexes:
            for col in cols:
                if ',' not in col and col in column_indexes:
                    duplicates.append((node.name, col, idx_name))
    
    return duplicates

def main():
    total = 0
    for py_file in sorted(APP_DIR.rglob("*.py")):
        if "backup" in str(py_file) or "__pycache__" in str(py_file) or ".before-fix" in str(py_file):
            continue
        dups = find_duplicate_indexes(py_file)
        if dups:
            for model, col, idx in dups:
                print(f"  {py_file.relative_to(APP_DIR)}: {model}.{col} -> {idx}")
            total += len(dups)
    
    print(f"\nTotal duplicates found: {total}")

if __name__ == "__main__":
    main()
