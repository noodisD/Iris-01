# Python 3.14 Incompatibility Report

## Issue Summary
The current system is running **Python 3.14.2**, which is too new for several core dependencies in this project. While Python 3.14 introduces performance improvements, many data science and AI libraries have not yet updated their build pipelines or codebases to support it.

## Specific Failures

### 1. `pypika` (SQL Query Builder)
*   **Error:** `AttributeError: module 'ast' has no attribute 'Str'`
*   **Cause:** Python 3.14 removed the `ast.Str` class (deprecated since 3.8), which `pypika` (v0.48.9) relies on.
*   **Impact:** Cannot build the package.

### 2. `onnxruntime` (AI Inference)
*   **Error:** `Unable to find installation candidates`
*   **Cause:** No pre-compiled binary wheels exist for Python 3.14 yet.
*   **Impact:** Cannot install the package.

### 3. `numpy` & `tokenizers`
*   **Issue:** Missing binary wheels, forcing a compilation from source which often fails due to C API changes in Python 3.14.

## Recommended Solution

You need to use **Python 3.11** (recommended) or **3.12**.

### Option A: Install via pyenv (Recommended)
If you can install `pyenv`, it allows managing multiple python versions easily.
```bash
# Install pyenv dependencies (Arch Linux)
sudo pacman -S --needed base-devel openssl zlib xz tk

# Install pyenv (if not installed) - see https://github.com/pyenv/pyenv#installation
curl https://pyenv.run | bash

# Install Python 3.11
pyenv install 3.11.9
pyenv local 3.11.9

# Re-run poetry
poetry env use 3.11.9
poetry install
```

### Option B: Conda / Mamba
If you use Conda:
```bash
conda create -n iris python=3.11
conda activate iris
poetry install
```
