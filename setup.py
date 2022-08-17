from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in rent_management/__init__.py
from rent_management import __version__ as version

setup(
	name="rent_management",
	version=version,
	description="Initially this app is made for Rent Management.",
	author="Gourav Saini",
	author_email="gourav.saini@omniflo.in",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
