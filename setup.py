"""
Setup file for Modpack Manager (mpm)
Install with: pip install git+https://github.com/yourusername/mpm.git
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="mpm-modpack-manager",
    version="1.0.1",
    author="AhmedShah29",
    description="A CLI tool for creating and managing Minecraft modpacks",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/AhmedShah29/MP-Manager",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Games/Entertainment",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.7",
    install_requires=[
        "requests>=2.25.0",
    ],
    entry_points={
        "console_scripts": [
            "mpm=mpm.__main__:main",
        ],
    },
    keywords="minecraft modpack modrinth fabric forge neoforge quilt mods",
    project_urls={
        "Bug Reports": "https://github.com/AhmedShah29/MP-Manager/issues",
        "Source": "https://github.com/AhmedShah29/MP-Manager",
    },
)
