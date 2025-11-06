"""
Renglo API
"""

from setuptools import setup, find_packages

setup(
    name="renglo-api",
    version="1.0.0",
    description="Generic Flask API layer for Renglo applications",
    author="Renglo Team",
    packages=find_packages(),
    python_requires=">=3.12",
    install_requires=[
        "renglo-lib>=1.0.0",  # Will be overridden in requirements.txt with git URL
        "Flask==3.1.0",
        "Flask-Cors==5.0.0",
        "Flask-Cognito==1.21",
        "Flask-Caching==2.1.0",
        "boto3==1.35.38",
        "zappa==0.59.0",
        "setuptools>=45.0.0,<81",
    ],
    include_package_data=True,
    package_data={
        'renglo_api': ['static/**/*'],
    },
)

