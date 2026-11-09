#!/usr/bin/env python3
"""Rename aliases for published cards.

GitHub keeps a repository's node id across account and repository renames,
while full_name -- and therefore our owner__repo slug -- changes with it.
Every published path (docs/p/<slug>.html, docs/badge/<slug>.json) is derived
from that slug, so treating a rename as remove-plus-add breaks every external
link to the old card (issue #17). The alias map records old slug -> current
slug so old paths can keep serving a redirect instead of being swept away.

Detection joins the previous and the current catalog on node_id: a repo whose
node id is unchanged but whose full_name moved was renamed. A repository that
was deleted and recreated under the same name mints a new node id and gets no
alias, which is the behaviour we want.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ALIASES = ROOT / 'data' / 'aliases.json'


def load(path=None):
    try:
        return json.loads((path or ALIASES).read_text())
    except Exception:
        return {}


def resolve(aliases, slug):
    """Follow a rename chain to its current slug; a cycle stops where it starts."""
    seen = set()
    while slug in aliases and slug not in seen:
        seen.add(slug)
        slug = aliases[slug]
    return slug


def detect(repos, previous):
    """(old_slug, new_slug) pairs for entries that kept their node id but moved."""
    previous_names = {r['node_id']: r['full_name'] for r in previous if r.get('node_id')}
    for r in repos:
        old = previous_names.get(r.get('node_id'))
        if old and old != r['full_name']:
            yield old.replace('/', '__'), r['full_name'].replace('/', '__')


def update(repos, previous, aliases=None):
    """Fold this run's renames into the map, preserving earlier entries.

    Targets are stored as discovered; chains are followed at read time, so a
    repo renamed twice yields A->B plus B->C and resolve() walks to C.
    """
    aliases = load() if aliases is None else aliases
    for old_slug, new_slug in detect(repos, previous):
        target = resolve(aliases, new_slug)
        if old_slug != target and aliases.get(old_slug) != target:
            aliases[old_slug] = target
    return aliases
