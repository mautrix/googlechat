import setuptools

from mautrix_googlechat.get_version import git_tag, git_revision, version, linkified_version

try:
    long_desc = open("README.md").read()
except IOError:
    long_desc = "Failed to read README.md"

with open("requirements.txt") as reqs:
    install_requires = reqs.read().splitlines()

with open("optional-requirements.txt") as reqs:
    extras_require = {}
    current = []
    for line in reqs.read().splitlines():
        if line.startswith("#/"):
            extras_require[line[2:]] = current = []
        elif not line or line.startswith("#"):
            continue
        else:
            current.append(line)

extras_require["all"] = list({dep for deps in extras_require.values() for dep in deps})

with open("mautrix_googlechat/version.py", "w") as version_file:
    version_file.write(f"""# Generated in setup.py

git_tag = {git_tag!r}
git_revision = {git_revision!r}
version = {version!r}
linkified_version = {linkified_version!r}
""")

setuptools.setup(
    name="mautrix-googlechat",
    version=version,
    url="https://github.com/mautrix/googlechat",
    project_urls={
        "Changelog": "https://github.com/mautrix/googlechat/blob/master/CHANGELOG.md",
    },

    author="Tulir Asokan",
    author_email="tulir@maunium.net",

    description="A Matrix-Google Chat puppeting bridge.",
    long_description=long_desc,
    long_description_content_type="text/markdown",

    packages=setuptools.find_packages(),

    install_requires=install_requires,
    extras_require=extras_require,
    python_requires="~=3.9",

    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)",
        "Topic :: Communications :: Chat",
        "Framework :: AsyncIO",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    package_data={"mautrix_googlechat": [
        "web/static/*.png", "web/static/*.css", "web/static/*.html", "web/static/*.js",
        "example-config.yaml"
    ]},
    data_files=[
        (".", ["mautrix_googlechat/example-config.yaml"]),
    ],
)
