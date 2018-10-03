"""This module contains helper functions."""

import subprocess
import logging
import requests

import itertools as it

from lxml import etree

from cpe import CPE

from nvdlib.utils import rgetattr
from cvejob.config import Config


logger = logging.getLogger(__name__)


def run_cpe2pkg(vendor, product):
    """Run cpe2pkg tool for given vendor and product.

    :return: list, up to 10 package name candidates
    """
    query_template = 'product:( {product} )  AND  vendor:( {vendor} )'
    p = ' '.join(product).replace(':', ' ')
    v = ' '.join(vendor).replace(':', ' ')
    query = query_template.format(product=p, vendor=v)

    pkgfile = '{pkgfile_dir}/{e}-packages'.format(
        pkgfile_dir=Config.pkgfile_dir,
        e=Config.ecosystem
    )

    logger.info(query)

    # run cpe2pkg tool with given query
    cpe2pkg_output = subprocess.check_output(
        'java -jar {cpe2pkg_path} --pkgfile {pkgfile} "{query}"'.format(
            cpe2pkg_path=Config.cpe2pkg_path,
            pkgfile=pkgfile,
            query=query
        ),
        shell=True,
        universal_newlines=True
    )
    cpe2pkg_lines = cpe2pkg_output.split('\n')
    results = []

    for line in cpe2pkg_lines:
        if not line:
            continue

        score, package = line.split()
        ecosystem = Config.ecosystem
        if ecosystem != 'java':
            package = package[len('{e}:'.format(e=ecosystem)):]
        results.append({'package': package, 'score': score})
    return results


# TODO: move all get_*_versions() to a shared library
def get_javascript_versions(package):
    """Get all versions for given package name."""
    url = 'https://registry.npmjs.org/{pkg_name}'.format(pkg_name=package)

    response = requests.get(url)

    if response.status_code != 200:
        logger.error('Unable to fetch versions for package {pkg_name}'.format(pkg_name=package))
        return []

    response_json = {}
    try:
        response_json = response.json()
    except ValueError:
        pass
    finally:
        if not response_json:
            return []

    versions = {x for x in response_json.get('versions', {})}

    return list(versions)


def get_python_versions(package):
    """Get all versions for given package name."""
    pypi_package_url = 'https://pypi.python.org/pypi/{pkg_name}/json'.format(pkg_name=package)

    response = requests.get(pypi_package_url)
    if response.status_code != 200:
        logger.error('Unable to obtain a list of versions for {pkg_name}'.format(pkg_name=package))
        return []

    return list({x for x in response.json().get('releases', {})})


def get_java_versions(package):
    """Get all versions for given groupId:artifactId."""
    try:
        g, a = package.split(':')
        g = g.replace('.', '/')

        filenames = {'maven-metadata.xml', 'maven-metadata-local.xml'}

        versions = set()
        ok = False
        for filename in filenames:

            url = 'http://repo1.maven.org/maven2/{g}/{a}/{f}'.format(g=g, a=a, f=filename)

            try:
                metadata_xml = etree.parse(url)
                ok = True  # We successfully downloaded the file
                version_elements = metadata_xml.findall('.//version')
                versions = versions.union({x.text for x in version_elements})
            except OSError:
                # Not both XML files have to exist, so don't freak out yet
                pass

        if not ok:
            logger.error(
                'Unable to obtain a list of versions for {package}'.format(package=package)
            )

        return list(versions)
    except ValueError:
        # wrong package specification etc.
        return []


def get_cpe(doc, cpe_type: str = None) -> list:
    """Get list of CPE objects.

    :param doc: Document, single Document object from Collection
    :param cpe_type: str, <type>
        <type>: any of (or abbreviation of) [application, hardware, operating_system]
    """
    valid_cpe_types = ['application', 'hardware', 'operating_system']
    if cpe_type and not isinstance(cpe_type, str):
        raise TypeError(f"`cpe_type` expected to be str, got: {type(cpe_type)}")

    type_to_check = None

    if cpe_type is not None:
        for t in valid_cpe_types:
            if t.startswith(cpe_type.lower()):
                type_to_check = t
                break

        if cpe_type and type_to_check is None:
            raise ValueError(
                f"`cpe_type` expected to be any of {valid_cpe_types}"
            )

    cpe_list = [
        CPE(cpe_str) for cpe_str in it.chain(*rgetattr(doc, 'configurations.nodes.data.cpe'))
    ]

    if type_to_check:
        cpe_list = list(filter(
            lambda _cpe: eval(f"_cpe.is_{type_to_check}()"),
            cpe_list
        ))

    return cpe_list


def get_description_by_lang(doc, lang='en'):
    """Get description for given language."""
    desc_data = rgetattr(doc, 'cve.descriptions.data')
    desc = None

    for node in desc_data:
        # if no lang value, assume english
        if getattr(node, 'lang', 'en') == lang:
            desc = getattr(node, 'value', None)
            break

    return desc
