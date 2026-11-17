from rest_framework import serializers

from agent.schemas import HumanDecision, RequiredDocument
from reviews.models import Checklist, Review, ReviewFile


class ChecklistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Checklist
        fields = ["slug", "name", "items"]


class ReviewFileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ReviewFile
        fields = ["id", "name", "url", "extraction_error"]

    def get_url(self, obj: ReviewFile) -> str:
        # Relative path, served by the API itself. Works behind any proxy.
        return f"/api/reviews/{obj.review_id}/files/{obj.id}/download/"


class ReviewListSerializer(serializers.ModelSerializer):
    checklist = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = Review
        fields = ["id", "candidate_name", "checklist", "status", "verdict", "created_at", "completed_at"]


class ReviewDetailSerializer(ReviewListSerializer):
    files = ReviewFileSerializer(many=True, read_only=True)
    requirements = serializers.JSONField(read_only=True)

    class Meta(ReviewListSerializer.Meta):
        fields = ReviewListSerializer.Meta.fields + [
            "error",
            "requirements",
            "files",
            "extracted_documents",
            "findings",
            "pending_review",
            "human_decisions",
            "resolved_findings",
            "report",
            "started_at",
            "updated_at",
        ]


class ReviewCreateSerializer(serializers.Serializer):
    candidate_name = serializers.CharField(max_length=200)
    checklist = serializers.SlugRelatedField(slug_field="slug", queryset=Checklist.objects.all())
    files = serializers.ListField(child=serializers.FileField(), allow_empty=True, required=False)

    def validate_checklist(self, checklist: Checklist) -> Checklist:
        for item in checklist.items:
            RequiredDocument.model_validate(item)
        return checklist


class DecisionsSerializer(serializers.Serializer):
    decisions = serializers.ListField(child=serializers.DictField(), allow_empty=True)

    def validate_decisions(self, decisions: list[dict]) -> list[dict]:
        try:
            return [HumanDecision.model_validate(d).model_dump() for d in decisions]
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
