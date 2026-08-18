"""Setup for older macOS system pip/setuptools."""

from setuptools import find_packages, setup

setup(
    name="aegis",
    version="1.2.0",
    description="Aegis agent OS — portable JIT token supply chain",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "aegis=aegis.cli:main",
        ],
    },
    extras_require={
        "dev": ["pytest>=7.0"],
        "treesitter": [
            "tree-sitter>=0.21",
            "tree-sitter-python",
            "tree-sitter-javascript",
            "tree-sitter-typescript",
        ],
    },
)
