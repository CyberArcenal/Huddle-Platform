# delete_migrations.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCLUDE_DIRS = {'.venv', 'venv', 'env'}  # add more kung iba pangalan ng virtualenv mo

for root, dirs, files in os.walk(BASE_DIR):
    # skip kung nasa loob ng excluded dirs
    if any(excluded in root for excluded in EXCLUDE_DIRS):
        continue

    if "migrations" in dirs:
        migrations_dir = os.path.join(root, "migrations")
        for filename in os.listdir(migrations_dir):
            file_path = os.path.join(migrations_dir, filename)
            if filename != "__init__.py" and filename.endswith(".py"):
                print(f"Deleting {file_path}")
                os.remove(file_path)
            elif filename.endswith(".pyc"):
                print(f"Deleting {file_path}")
                os.remove(file_path)