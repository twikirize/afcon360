import os
import shutil

def clear_python_cache(start_path):
    """
    Recursively deletes __pycache__ directories and .pyc files
    starting from the given path.
    """
    print(f"Starting cache cleanup in: {start_path}")
    deleted_count = 0
    deleted_size = 0

    for dirpath, dirnames, filenames in os.walk(start_path):
        # Delete __pycache__ directories
        if '__pycache__' in dirnames:
            cache_path = os.path.join(dirpath, '__pycache__')
            try:
                size = sum(os.path.getsize(os.path.join(cache_path, f)) for f in os.listdir(cache_path) if os.path.isfile(os.path.join(cache_path, f)))
                shutil.rmtree(cache_path)
                print(f"Deleted directory: {cache_path}")
                deleted_count += 1
                deleted_size += size
            except OSError as e:
                print(f"Error deleting {cache_path}: {e}")
            dirnames.remove('__pycache__') # Don't recurse into it

        # Delete .pyc files
        for filename in filenames:
            if filename.endswith('.pyc'):
                pyc_path = os.path.join(dirpath, filename)
                try:
                    size = os.path.getsize(pyc_path)
                    os.remove(pyc_path)
                    print(f"Deleted file: {pyc_path}")
                    deleted_count += 1
                    deleted_size += size
                except OSError as e:
                    print(f"Error deleting {pyc_path}: {e}")

    print(f"\nCache cleanup complete!")
    print(f"Deleted {deleted_count} items, freeing up approximately {deleted_size / (1024*1024):.2f} MB.")

if __name__ == "__main__":
    # Get the directory where this script is located (which should be your project root)
    project_root = os.path.dirname(os.path.abspath(__file__))
    clear_python_cache(project_root)
