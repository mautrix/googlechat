import setuptools
import mautrix_hangouts

try:
    long_desc = open("README.md").read()
except IOError:
    long_desc = "Failed to read README.md"

setuptools.setup(
    name="mautrix-hangouts",
    version=mautrix_hangouts.__version__,
    url="https://github.com/tulir/mautrix-hangouts",

    author="Tulir Asokan",
    author_email="tulir@maunium.net",

    description="A Matrix-Hangouts puppeting bridge.",
    long_description=long_desc,
    long_description_content_type="text/markdown",

    packages=setuptools.find_packages(),

    install_requires=[
        "aiohttp>=3.0.1,<4",
        "mautrix>=0.4.0.dev34,<0.5.0",
        "ruamel.yaml>=0.15.94,<0.16",
        "commonmark>=0.8,<0.9",
        "python-magic>=0.4,<0.5",
        "hangups>=0.4.9,<0.5.0",
        "SQLAlchemy>=1.2,<2",
        "alembic>=1,<2",
    ],

    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)",
        "Topic :: Communications :: Chat",
        "Framework :: AsyncIO",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
    entry_points="""
        [console_scripts]
        mautrix-hangouts=mautrix_hangouts.__main__:main
    """,
    package_data={"mautrix_hangouts": [
        "web/static/*.png", "web/static/*.css", "web/static/*.html", "web/static/*.js",
    ]},
    data_files=[
        (".", ["example-config.yaml"]),
    ],
)
