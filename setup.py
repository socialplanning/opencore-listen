from setuptools import setup, find_packages
import sys, os

version = '0.6.5dev'

f = open('README.txt')
readme = "".join(f.readlines())
f.close()

setup(name='Products.listen',
      version=version,
      description="listen is a mailing list product for Plone",
      long_description=readme,
      classifiers=[],
      keywords='',
      author='Robert Marianski',
      author_email='listen-dev at lists.coactivate.org',
      url='https://projects.openplans.org/listen',
      license='GPL',
      packages=find_packages(),
      namespace_packages=['Products'],
      include_package_data=True,
      zip_safe=False,
      dependency_links=[
        'https://svn.openplans.org/svn/vendor/Products.MailBoxer#egg=Products.MailBoxer-0.1vendor',
        'https://svn.openplans.org/svn/vendor/Products.ManageableIndex#egg=Products.ManageableIndex-0.1vendor',
        'https://svn.openplans.org/svn/vendor/Products.OFolder#egg=Products.OFolder-0.1vendor',
        ],
      install_requires=[
        'setuptools',
        'Products.MailBoxer==0.1vendor',
        'Products.ManageableIndex==0.1vendor',
        'Products.OFolder==0.1vendor',
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
