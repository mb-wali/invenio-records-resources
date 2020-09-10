# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 CERN.
# Copyright (C) 2020 Northwestern University.
#
# Invenio-Records-Resources is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see LICENSE file for more
# details.

"""Data access layer tests."""

from datetime import datetime

import pytest
from invenio_db import db
from invenio_indexer.api import RecordIndexer
from invenio_search import current_search_client
from jsonschema import ValidationError
from mock_module.api import Record


@pytest.fixture()
def example_data():
    """Example data."""
    return {
        'metadata': {'title': 'Test'}
    }


@pytest.fixture()
def example_record(db, example_data):
    """Example record."""
    record = Record.create(example_data, expires_at=datetime(2020, 9, 7, 0, 0))
    db.session.commit()
    return record


@pytest.fixture()
def indexer():
    """Indexer instance with correct Record class."""
    return RecordIndexer(record_cls=Record)


#
# Smoke tests
#
def test_record_empty(app, db):
    """Test record creation."""
    # Empty record creation works, and injects a schema.
    record = Record.create({})
    db.session.commit()
    assert record.schema

    # JSONSchema validation works.
    pytest.raises(ValidationError, Record.create, {'metadata': {'title': 1}})


def test_record_via_field(app, db):
    """Record creation via field."""
    record = Record.create({}, metadata={'title': 'test'})
    assert record.metadata == {'title': 'test'}


def test_record_indexing(app, db, es, example_record, indexer):
    """Test indexing of a record."""
    # Index document in ES
    assert indexer.index(example_record)['result'] == 'created'

    # Retrieve document from ES
    data = current_search_client.get(
        'records-record-v1.0.0', example_record.id)

    # Loads the ES data and compare
    record = Record.loads(data['_source'])
    assert record == example_record
    assert record.id == example_record.id
    assert record.revision_id == example_record.revision_id
    assert record.created == example_record.created
    assert record.updated == example_record.updated
    assert record.expires_at == example_record.expires_at

    # Check system fields
    record.metadata == example_record['metadata']


def test_record_delete_reindex(app, db, es, example_record, example_data,
                               indexer):
    """Test reindexing of a deleted record."""
    record = example_record

    # Index record
    assert indexer.index(record)['result'] == 'created'

    # Delete record.
    record.delete()
    db.session.commit()
    assert indexer.delete(record)['result'] == 'deleted'

    # Update record and reindex (this will cause troubles unless proper
    # optimistic concurrency control is used).
    record.undelete()
    record.commit()
    db.session.commit()
    assert indexer.index(record)['result'] == 'created'
