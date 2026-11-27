"""Management command to set part stock levels from a CSV file.

The CSV file lists the target stock quantity for each part (matched by IPN),
optionally with the stock location.  A file kept in your local (unversioned)
``userdata/part-list/stock_levels.csv`` holds the target inventory quantity
of each part.

The import is idempotent: running it again sets the same stock level instead
of adding to it.
"""

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from part.models import Part, PartCategory
from stock.models import StockItem, StockLocation

REQUIRED_COLUMNS = ['ipn', 'quantity']
DEFAULT_LOCATION = '主仓库'


class Command(BaseCommand):
    """Set part stock levels from a CSV file."""

    help = 'Set part stock levels from a CSV file'

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument('path', type=str, help='Path to the stock level CSV file')
        parser.add_argument(
            '--location',
            default=DEFAULT_LOCATION,
            help=f'Default stock location (default: {DEFAULT_LOCATION})',
        )
        parser.add_argument(
            '--create-missing',
            action='store_true',
            dest='create_missing',
            help='Create parts (and categories) which do not exist yet',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Validate the file and report what would be imported',
        )

    def read_rows(self, path: Path, default_location: str) -> list[dict]:
        """Read and validate the stock level CSV file."""
        try:
            with path.open(encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                headers = [str(header).strip() for header in (reader.fieldnames or [])]
                raw_rows = [
                    {
                        str(key).strip(): (value or '').strip()
                        for key, value in row.items()
                    }
                    for row in reader
                    if any((value or '').strip() for value in row.values())
                ]
        except FileNotFoundError as exc:
            raise CommandError(f'Stock level file not found: {path}') from exc
        except UnicodeDecodeError as exc:
            raise CommandError(f'Stock level file is not valid UTF-8: {path}') from exc

        missing = [column for column in REQUIRED_COLUMNS if column not in headers]

        if missing:
            raise CommandError(
                f'Missing required columns: {", ".join(missing)} '
                f'(found: {", ".join(headers)})'
            )

        rows = []
        errors = []
        seen = set()

        for line, raw in enumerate(raw_rows, start=2):
            ipn = raw.get('ipn', '')

            if not ipn:
                errors.append(f'line {line}: empty ipn')
                continue

            try:
                quantity = Decimal(raw.get('quantity', ''))
            except (InvalidOperation, ValueError):
                errors.append(
                    f'line {line}: invalid quantity {raw.get("quantity", "")}'
                )
                continue

            if quantity < 0:
                errors.append(f'line {line}: negative quantity {quantity}')
                continue

            location = raw.get('location') or default_location

            if (ipn, location) in seen:
                errors.append(f'line {line}: duplicate IPN {ipn} for {location}')

            seen.add((ipn, location))

            rows.append({
                'ipn': ipn,
                'quantity': quantity,
                'location': location,
                'name': raw.get('name', ''),
                'category': raw.get('category', ''),
            })

        if errors:
            raise CommandError('Invalid stock level file:\n' + '\n'.join(errors))

        return rows

    def handle(self, *args, **kwargs):
        """Import the stock levels."""
        path = Path(kwargs['path']).expanduser()

        if not path.is_file():
            raise CommandError(f'Stock level file not found: {path}')

        rows = self.read_rows(path, kwargs['location'])
        create_missing = kwargs.get('create_missing', False)
        dry_run = kwargs.get('dry_run', False)

        parts = {part.IPN: part for part in Part.objects.all()}
        missing = sorted({row['ipn'] for row in rows if row['ipn'] not in parts})

        if missing and not create_missing:
            raise CommandError(
                'Unknown part IPNs (use --create-missing to create them): '
                + ', '.join(missing)
            )

        for row in rows:
            if row['ipn'] in missing and not row['name']:
                raise CommandError(
                    f'Part {row["ipn"]} does not exist and no name was provided'
                )

        if dry_run:
            create_note = f', creating {len(missing)} parts' if missing else ''
            self.stdout.write(
                self.style.WARNING(
                    f'Dry run: would set stock for {len(rows)} parts{create_note}'
                    f' across {len({row["location"] for row in rows})} locations'
                )
            )
            return

        created_parts = 0
        created_stock = 0
        updated_stock = 0
        unchanged = 0
        skipped_zero = 0

        with transaction.atomic():
            locations = {}
            categories = {}

            for row in rows:
                if row['ipn'] not in parts:
                    category = None

                    if row['category']:
                        category = categories.get(row['category'])

                        if category is None:
                            category, _ = PartCategory.objects.get_or_create(
                                name=row['category']
                            )
                            categories[row['category']] = category

                    parts[row['ipn']] = Part.objects.create(
                        IPN=row['ipn'],
                        name=row['name'],
                        description=row['name'],
                        category=category,
                    )
                    created_parts += 1

            for row in rows:
                location = locations.get(row['location'])

                if location is None:
                    location, _ = StockLocation.objects.get_or_create(
                        name=row['location']
                    )
                    locations[row['location']] = location

                part = parts[row['ipn']]
                items = list(
                    StockItem.objects.filter(part=part, location=location).order_by(
                        'pk'
                    )
                )
                current = sum((item.quantity for item in items), Decimal(0))
                target = row['quantity']

                if current == target:
                    unchanged += 1
                elif items:
                    # Adjust the first stock item so the total matches the target
                    first = items[0]
                    first.quantity += target - current
                    first.save()
                    updated_stock += 1
                elif target > 0:
                    StockItem.objects.create(
                        part=part, location=location, quantity=target
                    )
                    created_stock += 1
                else:
                    skipped_zero += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Imported {len(rows)} stock levels '
                f'({created_parts} parts created, '
                f'{created_stock} stock items created, '
                f'{updated_stock} updated, {unchanged} unchanged, '
                f'{skipped_zero} zero skipped)'
            )
        )
