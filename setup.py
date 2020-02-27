import setuptools
import glob

from mautrix_hangouts.get_version import git_tag, git_revision, version, linkified_version

try:
    long_desc = open("README.md").read()
except IOError:
    long_desc = "Failed to read README.md"

with open("mautrix_hangouts/version.py", "w") as version_file:
    version_file.write(f"""# Generated in setup.py

git_tag = {git_tag!r}
git_revision = {git_revision!r}
version = {version!r}
linkified_version = {linkified_version!r}
""")

setuptools.setup(
    name="mautrix-hangouts",
    version=version,
    url="https://github.com/tulir/mautrix-hangouts",

    author="Tulir Asokan",
    author_email="tulir@maunium.net",

    description="A Matrix-Hangouts puppeting bridge.",
    long_description=long_desc,
    long_description_content_type="text/markdown",

    packages=setuptools.find_packages(),

    install_requires=[
        "aiohttp>=3,<4",
        "mautrix>=0.4.1,<0.5.0",
        "ruamel.yaml>=0.15.94,<0.17",
        "commonmark>=0.8,<0.10",
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
        "Programming Language :: Python :: 3.8",
    ],
    entry_points="""
        [console_scripts]
        mautrix-hangouts=mautrix_hangouts.__main__:main
    """,
    package_data={"mautrix_hangouts": [
        "web/static/*.png", "web/static/*.css", "web/static/*.html", "web/static/*.js",
    ]},
    data_files=[
        (".", ["example-config.yaml", "alembic.ini"]),
        ("alembic", ["alembic/env.py"]),
        ("alembic/versions", glob.glob("alembic/versions/*.py"))
    ],
)
