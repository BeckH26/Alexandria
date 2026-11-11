from setuptools import setup, find_packages

setup(
    name="alexandria-media",
    version="1.0.0",
    packages=find_packages(),
    py_modules=["cli", "progress", "scraper", "run"],
    package_data={
        "providers": ["tokyoinsider_catalog.json"],
    },
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "alexandria = run:main",
        ],
    },
)
