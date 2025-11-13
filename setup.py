from setuptools import setup

setup(
    name="kalshi-bot",
    version="0.1.0",
    py_modules=["main", "kalshi_client", "config"],
    install_requires=[
        "requests>=2.31.0",
        "cryptography>=42.0.5",
        "python-dotenv>=1.0.1",
        "rich>=13.6.0",
    ],
    entry_points={
        "console_scripts": [
            # command name = module:function
            "kalshi=main:main",
        ],
    },
)
