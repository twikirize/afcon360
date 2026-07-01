import os

def generate_clean_tree(root_dir, exclude_dirs=None, exclude_files=None):
    if exclude_dirs is None:
        exclude_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env', 'migrations', 'docs', 'scripts', 'Readme', 'reports', 'mcps', 'pushups', 'static', 'templates', 'docker', 'kilocmds', 'tests', 'saved_work', 'backup', 'Documentation'}
    if exclude_files is None:
        exclude_files = {'.pyc', '.pyo', '.bak', '.backup', '.old', '~', '.md'}
    
    lines = []
    lines.append('# AFCON360 Project Tree (Clean)')
    lines.append('')
    lines.append('```')
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Filter out excluded directories
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs and not any(d.endswith(ext) for ext in exclude_files)]
        
        rel_path = os.path.relpath(dirpath, root_dir)
        if rel_path == '.':
            continue
            
        level = rel_path.count(os.sep)
        indent = '    ' * level
        lines.append(f'{indent}{os.path.basename(dirpath)}/')
        
        sub_indent = '    ' * (level + 1)
        for f in sorted(filenames):
            if not any(f.endswith(ext) for ext in exclude_files):
                lines.append(f'{sub_indent}{f}')
    
    lines.append('```')
    return '\n'.join(lines)

# Generate clean tree
tree = generate_clean_tree('app')
with open('tree_clean.md', 'w', encoding='utf-8') as f:
    f.write(tree)
print('Generated tree_clean.md')