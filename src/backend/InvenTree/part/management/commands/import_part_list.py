"""Management command to import a part list from a CSV file.

The CSV file is a normalised part list (one row per part), for example the
``userdata/part-list/parts.csv`` file kept in your local (unversioned) user data
directory.  Each row creates (or updates) a part, its category and the part
parameters which are defined by the list.

The import is idempotent: running it again updates the existing parts (matched
by IPN) and their parameter values instead of creating duplicates.
"""

import csv
from pathlib import Path

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from common.models import Parameter, ParameterTemplate
from part.models import Part, PartCategory

# CSV column -> (part parameter template name, template description)
PARAMETER_COLUMNS = {
    'part_type': ('器件类型', '元件类型 / part type'),
    'value': ('值/型号', '元件值或型号 / value or MPN'),
    'footprint': ('封装', 'PCB 封装 / footprint'),
    'designators': ('位号', 'BOM 位号 / reference designators'),
    'quantity': ('用量', '单板用量 / quantity per assembly'),
    'notes': ('备注', '导入备注 / notes'),
}

REQUIRED_COLUMNS = ['ipn', 'category', 'name']


class Command(BaseCommand):
    """Import parts and part parameters from a normalised part list CSV file."""

    help = 'Import parts and part parameters from a CSV part list'

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument('path', type=str, help='Path to the part list CSV file')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Validate the file and report what would be imported',
        )

    def read_rows(self, path: Path) -> list[dict]:
        """Read and validate the part list CSV file."""
        try:
            with path.open(encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                headers = [str(header).strip() for header in (reader.fieldnames or [])]
                rows = [
                    {
                        str(key).strip(): (value or '').strip()
                        for key, value in row.items()
                    }
                    for row in reader
                    if any((value or '').strip() for value in row.values())
                ]
        except FileNotFoundError as exc:
            raise CommandError(f'Part list file not found: {path}') from exc
        except UnicodeDecodeError as exc:
            raise CommandError(f'Part list file is not valid UTF-8: {path}') from exc

        missing = [column for column in REQUIRED_COLUMNS if column not in headers]

        if missing:
            raise CommandError(
                f'Missing required columns: {", ".join(missing)} '
                f'(found: {", ".join(headers)})'
            )

        imported_ipns = set()
        errors = []

        for line, row in enumerate(rows, start=2):
            empty = [column for column in REQUIRED_COLUMNS if not row.get(column)]

            if empty:
                errors.append(f'line {line}: empty {", ".join(empty)}')
                continue

            if row['ipn'] in imported_ipns:
                errors.append(f'line {line}: duplicate IPN {row["ipn"]}')

            imported_ipns.add(row['ipn'])

        if errors:
            raise CommandError('Invalid part list:\n' + '\n'.join(errors))

        return rows

    def handle(self, *args, **kwargs):
        """Import the part list."""
        path = Path(kwargs['path']).expanduser()

        if not path.is_file():
            raise CommandError(f'Part list file not found: {path}')

        rows = self.read_rows(path)
        categories = sorted({row['category'] for row in rows})

        if kwargs.get('dry_run'):
            self.stdout.write(
                self.style.WARNING(
                    f'Dry run: would import {len(rows)} parts into '
                    f'{len(categories)} categories ({", ".join(categories)})'
                )
            )
            return

        part_content_type = ContentType.objects.get_for_model(Part)

        created = 0
        updated = 0
        parameter_count = 0
        templates_created = 0

        with transaction.atomic():
            parameter_templates = {}

            for template_name, description in PARAMETER_COLUMNS.values():
                template, was_created = ParameterTemplate.objects.get_or_create(
                    name=template_name,
                    defaults={
                        'model_type': part_content_type,
                        'description': description,
                    },
                )

                if was_created:
                    templates_created += 1
                elif template.model_type_id is None:
                    template.model_type = part_content_type
                    template.save()

                parameter_templates[template_name] = template

            for category_name in categories:
                category, _ = PartCategory.objects.get_or_create(
                    name=category_name,
                    defaults={'description': f'{category_name} 零件清单'},
                )

                category_rows = [
                    row for row in rows if row['category'] == category_name
                ]

                for row in category_rows:
                    part, was_created = self.update_part(row, category)
                    created += 1 if was_created else 0
                    updated += 0 if was_created else 1

                    parameter_count += self.update_parameters(
                        part, row, part_content_type, parameter_templates
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f'Imported {len(rows)} parts '
                f'({created} created, {updated} updated) '
                f'in {len(categories)} categories; '
                f'{parameter_count} parameter values, '
                f'{templates_created} parameter templates created'
            )
        )

    @staticmethod
    def update_part(row: dict, category: PartCategory) -> tuple[Part, bool]:
        """Create or update a single part, matched by its IPN."""
        part = Part.objects.filter(IPN=row['ipn']).first()

        if part is None:
            return (
                Part.objects.create(
                    IPN=row['ipn'],
                    name=row['name'],
                    description=row.get('description', ''),
                    category=category,
                ),
                True,
            )

        part.name = row['name']
        part.description = row.get('description', '')
        part.category = category
        part.save()

        return part, False

    @staticmethod
    def update_parameters(
        part: Part,
        row: dict,
        part_content_type: ContentType,
        templates: dict[str, ParameterTemplate],
    ) -> int:
        """Create, update or remove the parameter values for a part."""
        count = 0

        for column, (template_name, _) in PARAMETER_COLUMNS.items():
            template = templates[template_name]
            value = row.get(column, '')
            parameter = Parameter.objects.filter(
                model_type=part_content_type, model_id=part.pk, template=template
            ).first()

            if value:
                if parameter is None:
                    Parameter.objects.create(
                        model_type=part_content_type,
                        model_id=part.pk,
                        template=template,
                        data=value,
                    )
                elif parameter.data != value:
                    parameter.data = value
                    parameter.save()

                count += 1
            elif parameter is not None:
                parameter.delete()

        return count
