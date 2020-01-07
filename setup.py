from setuptools import setup, find_packages
import sys, os

version = '0.8.0'

try:
    readme = open('README.rst').read()
    changes = open("CHANGES.txt").read()
    readme = "%s\n%s" % (changes, readme)
except:
    readme = ""

setup(name='opencore-listen',
      version=version,
      description="Listen is a mailing list product for Plone",
      long_description=readme,
      # Get more strings from
      # https://pypi.org/pypi?:action=list_classifiers
      classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Environment :: Plugins',
          'Environment :: Web Environment',
          'Framework :: Plone',
          'Framework :: Plone :: 3.3',
          'Framework :: Zope2',
          'Framework :: Zope3',
          'Intended Audience :: End Users/Desktop',
          'Intended Audience :: System Administrators',
          'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
          'Operating System :: OS Independent',
          'Programming Language :: Python',
          'Programming Language :: Python :: 2.4',
          'Programming Language :: Python :: 2.6',
          'Programming Language :: Python :: 2.7',
          'Topic :: Communications :: Email',
          'Topic :: Communications :: Email :: Email Clients (MUA)',
          'Topic :: Communications :: Email :: Mailing List Servers',
          'Topic :: Communications :: Email :: Mail Transport Agents',
          'Topic :: Office/Business :: Office Suites',
          'Topic :: Software Development :: Libraries :: Python Modules',
      ],
      keywords='zope plone mailing list product socialplanning opencore listen',
      author='Robert Marianski, Alec Mitchell, Chris Abraham, Rob Miller, Ethan Jucovy',
      author_email='listen-dev at lists.coactivate.org',
      url='https://www.coactivate.org/projects/listen/',
      license='GPL',
      packages=find_packages(),
      namespace_packages=['Products'],
      include_package_data=True,
      zip_safe=False,
      dependency_links=[
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

