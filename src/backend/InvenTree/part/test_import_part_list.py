"""Tests for the ``import_part_list`` management command."""

import csv
import tempfile
from pathlib import Path

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from common.models import Parameter, ParameterTemplate
from part.models import Part, PartCategory

FIELD_NAMES = [
    'ipn',
    'category',
    'name',
    'part_type',
    'value',
    'description',
    'footprint',
    'designators',
    'quantity',
    'notes',
]


def part_row(**overrides) -> dict:
    """Return a complete part row with sensible defaults."""
    row = {
        'ipn': 'SKU-001',
        'category': 'Radar Board',
        'name': 'Capacitor 10uF',
        'part_type': 'Capacitor',
        'value': '10uF/16V',
        'description': 'Capacitor 10uF, package 0603',
        'footprint': '0603',
        'designators': 'C1, C3, C8',
        'quantity': '3',
        'notes': '',
    }
    row.update(overrides)
    return row


class ImportPartListTest(TestCase):
    """Tests for importing a normalised part list."""

    def write_csv(
        self,
        directory: str,
        rows: list[dict],
        field_names: list[str] | None = None,
        encoding: str = 'utf-8',
    ) -> Path:
        """Write a part list CSV file and return its path."""
        path = Path(directory) / 'parts.csv'

        with path.open('w', encoding=encoding, newline='') as handle:
            writer = csv.DictWriter(
                handle, fieldnames=field_names or FIELD_NAMES, lineterminator='\n'
            )
            writer.writeheader()
            writer.writerows(rows)

        return path

    def test_import_creates_category_parts_and_parameters(self):
        """Importing a part list creates parts and their parameter values."""
        rows = [
            part_row(),
            part_row(
                ipn='SKU-002',
                name='Resistor 1K',
                part_type='Resistor',
                value='1K',
                description='Resistor 1K, package 0201',
                footprint='0201',
                designators='R1, R7',
                quantity='4',
            ),
        ]

        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, rows)
            call_command('import_part_list', str(path), verbosity=0)

        category = PartCategory.objects.get(name='Radar Board')
        self.assertEqual(Part.objects.count(), 2)

        part = Part.objects.get(IPN='SKU-001')
        self.assertEqual(part.name, 'Capacitor 10uF')
        self.assertEqual(part.description, 'Capacitor 10uF, package 0603')
        self.assertEqual(part.category, category)

        part_content_type = ContentType.objects.get_for_model(Part)
        parameters = {
            parameter.template.name: parameter
            for parameter in Parameter.objects.filter(
                model_type=part_content_type, model_id=part.pk
            )
        }

        self.assertEqual(
            set(parameters), {'Component Type', '值/型号', '封装', '位号', '用量'}
        )
        self.assertEqual(parameters['Component Type'].data, 'Capacitor')
        self.assertEqual(parameters['值/型号'].data, '10uF/16V')
        self.assertEqual(parameters['封装'].data, '0603')
        self.assertEqual(parameters['位号'].data, 'C1, C3, C8')

        quantity = parameters['用量']
        self.assertEqual(quantity.data, '3')
        self.assertEqual(quantity.data_numeric, 3.0)

        template = ParameterTemplate.objects.get(name='封装')
        self.assertEqual(template.model_type, part_content_type)

    def test_import_is_idempotent(self):
        """Running the import twice does not duplicate parts or parameters."""
        rows = [part_row()]

        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, rows)
            call_command('import_part_list', str(path), verbosity=0)
            call_command('import_part_list', str(path), verbosity=0)

        self.assertEqual(Part.objects.filter(IPN='SKU-001').count(), 1)
        self.assertEqual(
            ParameterTemplate.objects.filter(
                name__in=[name for name, _ in _parameter_columns()]
            ).count(),
            len(_parameter_columns()),
        )
        self.assertEqual(
            Parameter.objects.filter(
                model_type=ContentType.objects.get_for_model(Part),
                model_id=Part.objects.get(IPN='SKU-001').pk,
            ).count(),
            5,
        )

    def test_import_updates_and_removes_parameters(self):
        """An existing part is updated, and cleared values remove parameters."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [part_row()])
            call_command('import_part_list', str(path), verbosity=0)

            path = self.write_csv(
                directory,
                [
                    part_row(
                        name='Capacitor 10uF updated',
                        description='更新后的描述',
                        designators='C1',
                    )
                ],
            )
            call_command('import_part_list', str(path), verbosity=0)

        part = Part.objects.get(IPN='SKU-001')
        self.assertEqual(part.name, 'Capacitor 10uF updated')
        self.assertEqual(part.description, '更新后的描述')

        part_content_type = ContentType.objects.get_for_model(Part)
        parameters = {
            parameter.template.name: parameter.data
            for parameter in Parameter.objects.filter(
                model_type=part_content_type, model_id=part.pk
            )
        }

        self.assertEqual(parameters['位号'], 'C1')
        self.assertEqual(parameters['用量'], '3')

    def test_import_removes_parameter_when_value_is_cleared(self):
        """Clearing a column removes the matching parameter value."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [part_row()])
            call_command('import_part_list', str(path), verbosity=0)

            path = self.write_csv(directory, [part_row(notes='', designators='')])
            call_command('import_part_list', str(path), verbosity=0)

        part = Part.objects.get(IPN='SKU-001')
        part_content_type = ContentType.objects.get_for_model(Part)
        self.assertFalse(
            Parameter.objects.filter(
                model_type=part_content_type, model_id=part.pk, template__name='位号'
            ).exists()
        )

    def test_import_dry_run(self):
        """A dry run validates the file without writing any data."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [part_row()])
            call_command('import_part_list', str(path), dry_run=True, verbosity=0)

        self.assertFalse(Part.objects.exists())
        self.assertFalse(PartCategory.objects.exists())
        self.assertFalse(ParameterTemplate.objects.exists())

    def test_import_accepts_utf8_bom(self):
        """A CSV file saved with a UTF-8 byte-order mark is accepted."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [part_row()], encoding='utf-8-sig')
            call_command('import_part_list', str(path), verbosity=0)

        self.assertTrue(Part.objects.filter(IPN='SKU-001').exists())

    def test_import_requires_columns(self):
        """A file without the required columns is rejected."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(
                directory,
                [{'ipn': 'SKU-001', 'category': 'Radar Board'}],
                field_names=['ipn', 'category'],
            )

            with self.assertRaises(CommandError):
                call_command('import_part_list', str(path), verbosity=0)

        self.assertFalse(Part.objects.exists())

    def test_import_rejects_duplicate_ipn(self):
        """Two rows with the same IPN are rejected."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [part_row(), part_row()])

            with self.assertRaises(CommandError):
                call_command('import_part_list', str(path), verbosity=0)

        self.assertFalse(Part.objects.exists())

    def test_import_rejects_empty_required_value(self):
        """A row with an empty required value is rejected."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [part_row(name='')])

            with self.assertRaises(CommandError):
                call_command('import_part_list', str(path), verbosity=0)

        self.assertFalse(Part.objects.exists())

    def test_import_missing_file(self):
        """A missing part list file raises a CommandError."""
        with self.assertRaises(CommandError):
            call_command('import_part_list', 'does-not-exist.csv', verbosity=0)


def _parameter_columns() -> list[tuple[str, str]]:
    """Return the parameter columns defined by the command."""
    from part.management.commands.import_part_list import PARAMETER_COLUMNS

    return list(PARAMETER_COLUMNS.values())
