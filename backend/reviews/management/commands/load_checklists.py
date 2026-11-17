"""Load the checklists shipped in agent/checklists into the database."""

import json

from django.conf import settings
from django.core.management.base import BaseCommand

from agent.schemas import RequiredDocument
from reviews.models import Checklist


class Command(BaseCommand):
    help = "Create or update the checklists from agent/checklists/*.json"

    def handle(self, *args, **options):
        for path in sorted(settings.CHECKLISTS_DIR.glob("*.json")):
            items = [RequiredDocument.model_validate(i).model_dump() for i in json.loads(path.read_text())]
            name = path.stem.replace("_", " ").replace("-", " ").capitalize()
            checklist, created = Checklist.objects.update_or_create(
                slug=path.stem, defaults={"name": name, "items": items}
            )
            verb = "Created" if created else "Updated"
            self.stdout.write(f"{verb} checklist {checklist.slug} ({len(items)} items)")
