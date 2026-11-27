"""Tests for the ``import_stock_list`` management command."""

import csv
import tempfile
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from part.models import Part, PartCategory
from stock.models import StockItem, StockLocation

FIELD_NAMES = ['ipn', 'quantity', 'name', 'category', 'location']


def stock_row(**overrides) -> dict:
    """Return a complete stock row with sensible defaults."""
    row = {
        'ipn': 'SKU-001',
        'quantity': '28',
        'name': '',
        'category': '',
        'location': '主仓库',
    }
    row.update(overrides)
    return row


class ImportStockListTest(TestCase):
    """Tests for setting stock levels from a CSV file."""

    def setUp(self):
        """Create a part and stock location used by the tests."""
        self.category = PartCategory.objects.create(name='电子元件')
        self.part = Part.objects.create(
            IPN='SKU-001', name='Capacitor 10uF', category=self.category
        )
        self.location = StockLocation.objects.create(name='主仓库')

    def write_csv(
        self,
        directory: str,
        rows: list[dict],
        field_names: list[str] | None = None,
        encoding: str = 'utf-8',
    ) -> Path:
        """Write a stock level CSV file and return its path."""
        path = Path(directory) / 'stock.csv'

        with path.open('w', encoding=encoding, newline='') as handle:
            writer = csv.DictWriter(
                handle, fieldnames=field_names or FIELD_NAMES, lineterminator='\n'
            )
            writer.writeheader()
            writer.writerows(rows)

        return path

    def test_import_creates_stock(self):
        """A stock item is created for the target quantity."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [stock_row()])
            call_command('import_stock_list', str(path), verbosity=0)

        item = StockItem.objects.get(part=self.part, location=self.location)
        self.assertEqual(item.quantity, Decimal('28'))

    def test_import_updates_existing_stock(self):
        """An existing stock item is set to the target quantity."""
        StockItem.objects.create(part=self.part, location=self.location, quantity=5)

        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [stock_row(quantity='28')])
            call_command('import_stock_list', str(path), verbosity=0)

        item = StockItem.objects.get(part=self.part, location=self.location)
        self.assertEqual(item.quantity, Decimal('28'))

    def test_import_sets_total_across_multiple_items(self):
        """The total across multiple stock items is set to the target."""
        StockItem.objects.create(part=self.part, location=self.location, quantity=3)
        StockItem.objects.create(part=self.part, location=self.location, quantity=5)

        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [stock_row(quantity='10')])
            call_command('import_stock_list', str(path), verbosity=0)

        total = sum(
            item.quantity
            for item in StockItem.objects.filter(part=self.part, location=self.location)
        )
        self.assertEqual(total, Decimal('10'))

    def test_import_is_idempotent(self):
        """Running the import twice does not duplicate stock items."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [stock_row()])
            call_command('import_stock_list', str(path), verbosity=0)
            call_command('import_stock_list', str(path), verbosity=0)

        self.assertEqual(
            StockItem.objects.filter(part=self.part, location=self.location).count(), 1
        )
        self.assertEqual(
            StockItem.objects.get(part=self.part, location=self.location).quantity,
            Decimal('28'),
        )

    def test_import_creates_missing_parts(self):
        """Missing parts can be created when --create-missing is used."""
        rows = [
            stock_row(ipn='ASSY-100', quantity='17', name='Assembly board', category='整机')
        ]

        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, rows)
            call_command(
                'import_stock_list', str(path), create_missing=True, verbosity=0
            )

        part = Part.objects.get(IPN='ASSY-100')
        self.assertEqual(part.name, 'Assembly board')
        self.assertEqual(part.category.name, '整机')
        self.assertEqual(
            StockItem.objects.get(part=part, location=self.location).quantity,
            Decimal('17'),
        )

    def test_import_unknown_part_requires_flag(self):
        """An unknown part is rejected without --create-missing."""
        rows = [stock_row(ipn='ASSY-100', name='Assembly board', category='整机')]

        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, rows)

            with self.assertRaises(CommandError):
                call_command('import_stock_list', str(path), verbosity=0)

        self.assertFalse(Part.objects.filter(IPN='ASSY-100').exists())
        self.assertFalse(StockItem.objects.filter(part=self.part).exists())

    def test_import_requires_name_for_new_part(self):
        """A missing part without a name is rejected."""
        rows = [stock_row(ipn='ASSY-200', name='', category='整机')]

        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, rows)

            with self.assertRaises(CommandError):
                call_command(
                    'import_stock_list', str(path), create_missing=True, verbosity=0
                )

        self.assertFalse(Part.objects.filter(IPN='ASSY-200').exists())

    def test_import_zero_quantity_creates_no_item(self):
        """A zero quantity does not create an empty stock item."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [stock_row(quantity='0')])
            call_command('import_stock_list', str(path), verbosity=0)

        self.assertFalse(
            StockItem.objects.filter(part=self.part, location=self.location).exists()
        )

    def test_import_dry_run(self):
        """A dry run validates the file without writing any data."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [stock_row()])
            call_command('import_stock_list', str(path), dry_run=True, verbosity=0)

        self.assertFalse(StockItem.objects.exists())

    def test_import_accepts_utf8_bom(self):
        """A CSV file saved with a UTF-8 byte-order mark is accepted."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [stock_row()], encoding='utf-8-sig')
            call_command('import_stock_list', str(path), verbosity=0)

        self.assertTrue(
            StockItem.objects.filter(part=self.part, location=self.location).exists()
        )

    def test_import_rejects_invalid_quantity(self):
        """A non-numeric quantity is rejected."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [stock_row(quantity='abc')])

            with self.assertRaises(CommandError):
                call_command('import_stock_list', str(path), verbosity=0)

        self.assertFalse(StockItem.objects.exists())

    def test_import_rejects_negative_quantity(self):
        """A negative quantity is rejected."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [stock_row(quantity='-1')])

            with self.assertRaises(CommandError):
                call_command('import_stock_list', str(path), verbosity=0)

        self.assertFalse(StockItem.objects.exists())

    def test_import_requires_columns(self):
        """A file without the required columns is rejected."""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [{'ipn': 'SKU-001'}], field_names=['ipn'])

            with self.assertRaises(CommandError):
                call_command('import_stock_list', str(path), verbosity=0)

        self.assertFalse(StockItem.objects.exists())

    def test_import_missing_file(self):
        """A missing stock level file raises a CommandError."""
        with self.assertRaises(CommandError):
            call_command('import_stock_list', 'does-not-exist.csv', verbosity=0)
