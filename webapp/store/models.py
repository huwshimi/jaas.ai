import collections
import os
import re

import gfm
from jujubundlelib import references
from theblues.charmstore import CharmStore
from theblues.errors import EntityNotFound

cs = CharmStore("https://api.jujucharms.com/v5")


def get_charm_or_bundle(reference):
    try:
        entity_data = cs.entity(reference, True)
        return _parse_charm_or_bundle(entity_data)
    except EntityNotFound:
        return None


def _parse_charm_or_bundle(entity_data):
    meta = entity_data.get('Meta', None)
    is_charm = meta.get('charm-metadata', False)
    if is_charm:
        return _parse_charm_data(entity_data)
    else:
        return _parse_bundle_data(entity_data)


def _parse_bundle_data(bundle_data):
    bundle_id = bundle_data['Id']
    ref = references.Reference.from_string(bundle_id)
    name = ref.name
    revision_list = bundle_data['Meta']['revision-info'].get('Revisions')
    latest_revision = {
        'id': int(revision_list[0].split('-')[-1]),
        'full_id': revision_list[0],
        'url': '{}/{}'.format(
            ref.name,
            int(revision_list[0].split('-')[-1])
        )}

    bundle = {
        'archive_url': cs.archive_url(ref),
        'bundle_data': bundle_data,
        'bundle_visulisation': getBundleVisualization(ref),
        'display_name': _get_display_name(name),
        'revision_number': ref.revision,
        'files': _get_entity_files(ref, bundle_data['Meta']['manifest']),
        'latest_revision': latest_revision,
        'card_id': ref.path(),
        'readme': _render_markdown(
            cs.entity_readme_content(bundle_id)
        ),
        'services': _parseBundleServices(
            bundle_data['Meta']['bundle-metadata']['applications']
        ),
        'is_charm': False
    }

    return bundle


def _parseBundleServices(services):
    for k, v in services.items():
        ref = references.Reference.from_string(v['Charm'])
        v['Charm'] = ref.path()
        v['icon'] = cs.charm_icon_url(v['Charm'])
        v['url'] = ref.jujucharms_id()
        v['display_name'] = _get_display_name(k)

    return services


def _parse_charm_data(charm_data):
    charm_id = charm_data['Id']
    ref = references.Reference.from_string(charm_id)
    meta = charm_data.get('Meta', None)
    bzr_url, revisions = _extract_from_extrainfo(meta, ref)
    bugs_url, homepage = _extract_from_commoninfo(meta)
    revision_list = meta['revision-info'].get('Revisions')
    latest_revision = {
        'id': int(revision_list[0].split('-')[-1]),
        'full_id': revision_list[0],
        'url': '{}/{}'.format(
            meta['charm-metadata']['Name'],
            int(revision_list[0].split('-')[-1])
        )}

    charm = {
        'archive_url': cs.archive_url(ref),
        'bugs_url': bugs_url,
        'bzr_url': bzr_url,
        'charm_data': charm_data,
        'files': _get_entity_files(ref, meta['manifest']),
        'homepage': homepage,
        'icon': cs.charm_icon_url(charm_id),
        'id': charm_id,
        'card_id': ref.path(),
        'latest_revision': latest_revision,
        'options': meta.get('charm-config', {}).get('Options'),
        'owner': charm_data.get('owner', {}).get('User'),
        'provides': meta['charm-metadata'].get('Provides'),
        'requires': meta['charm-metadata'].get('Requires'),
        'resources': _extract_resources(ref, meta.get('resources', {})),
        'readme': _render_markdown(
            cs.entity_readme_content(charm_id)
        ),
        'revision_list': revision_list,
        'revision_number': ref.revision,
        'revisions': revisions,
        'series': meta.get('supported-series', {}).get('SupportedSeries'),
        'is_charm': True
    }

    return charm


def _get_entity_files(ref, manifest=None):
    try:
        files = cs.files(ref, manifest=manifest) or {}
        files = collections.OrderedDict(
            sorted(files.items())
        )
    except EntityNotFound:
        files = {}
    return files


def getBundleVisualization(ref, fetch=False):
    """Get the url for the bundle visualization, or the actual svg.
        :param ref The reference of the bundle to get the visualization for.
        :param fetch Whether or not to get the actual svg.
        :returns the URL or the SVG for the bundle visualisation
    """
    if not fetch:
        return cs.bundle_visualization_url(ref)
    try:
        return cs.bundle_visualization(ref)
    except EntityNotFound:
        return None


def _extract_resources(ref, resources):
    """Extract data from resources metadata.
        :param ref: The reference of the entity.
        :param resources: the resources metadata associated with the entity.
        :returns: a dictionary of resource name and an array containing
                the file extension, the file link of the resource.
    """
    result = {}
    for resource in resources:
        resource_url = ""
        if resource['Revision'] >= 0:
            resource_url = cs.resource_url(
                ref,
                resource['Name'],
                resource['Revision']
            )
        result[resource['Name']] = [
            os.path.splitext(resource['Path'])[1],
            resource_url
        ]

    return result


def _get_display_name(name):
    """Clean the name of the charm for readability.
        :param name the charm/bundle name.
        :return a cleaned name for display.
    """
    return name.replace('-', ' ')


def _get_bug_url(name, bugs_url):
    """Create a link to the bug tracker on Launchpad.
        :param name: the charm name.
        :returns: a URL for the bug tracker.
    """
    if bugs_url:
        return bugs_url
    return 'https://bugs.launchpad.net/charms/+source/{}'.format(name)


def _render_markdown(content):
    html = gfm.markdown(content)

    try:
        html = _convert_http_to_https(html)
    except Exception:
        # Leave the readme unparsed.
        pass

    return html


def _convert_http_to_https(content):
    """Convert any non secure inclusion of assets to secure.
        :param content: the content to parse as a string.
        :returns: the parsed content with http replaces with https
    """
    insensitive_link = re.compile(re.escape('src="http:'), re.IGNORECASE)
    content = insensitive_link.sub('src="https:', content)
    insensitive_link = re.compile(re.escape("src='http:"), re.IGNORECASE)
    content = insensitive_link.sub("src='https:", content)
    return content


def _extract_from_extrainfo(charm_data, ref):
    extra_info = charm_data.get('extra-info', {})
    revisions = (
        extra_info.get('bzr-revisions') or
        extra_info.get('vcs-revisions')
    )
    bzr_url = extra_info.get('bzr-url')
    return bzr_url, revisions


def _extract_from_commoninfo(bundle_data):
    common_info = bundle_data.get('common-info', {})
    bugs_url = common_info.get('bugs-url')
    homepage = common_info.get('homepage')
    return bugs_url, homepage
