"""Compatibility shim for older pip versions used by local Python 3.9 images."""

from setuptools import find_packages, setup


setup(
    name="patient-ops-agent",
    version="0.1.0",
    description="A stateful patient appointment operations agent",
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.9",
    install_requires=[
        "fastapi>=0.115,<1",
        "httpx>=0.28,<1",
        "langgraph>=0.2,<1",
        "pydantic>=2.10,<3",
        "pydantic-settings>=2.6,<3",
        "PyYAML>=6.0,<7",
        "sqlalchemy>=2.0,<3",
        "uvicorn>=0.34,<1",
    ],
    extras_require={
        "dev": ["pytest>=8,<9", "pytest-asyncio>=0.24,<2"],
        "postgres": ["psycopg[binary]>=3.2,<4"],
    },
    entry_points={
        "console_scripts": [
            "patient-ops-agent=patient_ops_agent.main:run",
            "patient-ops-worker=patient_ops_agent.worker:run",
            "patient-ops-token=patient_ops_agent.token_cli:run",
        ]
    },
)
